import Foundation

/// One bubble in the chat. Mirrors the messages `sphero-dev serve` returns
/// (see `src/sphero_dev/serve.py`); `id` and `date` are added on this side.
public struct ChatMessage: Codable, Identifiable, Equatable, Sendable {
    public enum Role: String, Codable, Sendable {
        case user, assistant, status, error
    }

    public var id: UUID
    public var role: Role
    public var parts: [Part]
    public var date: Date

    public init(role: Role, parts: [Part], id: UUID = UUID(), date: Date = Date()) {
        self.id = id
        self.role = role
        self.parts = parts
        self.date = date
    }

    public static func text(_ role: Role, _ text: String) -> ChatMessage {
        ChatMessage(role: role, parts: [.text(text)])
    }

    enum CodingKeys: String, CodingKey { case id, role, parts, date }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        role = (try? c.decode(Role.self, forKey: .role)) ?? .assistant
        parts = try c.decode([Part].self, forKey: .parts)
        date = try c.decodeIfPresent(Date.self, forKey: .date) ?? Date()
    }

    /// The program in this message, if it has one.
    public var code: CodePart? {
        for case .code(let c) in parts { return c }
        return nil
    }
}

public struct CodePart: Codable, Equatable, Sendable {
    public var language: String
    public var title: String?
    public var code: String

    public init(language: String = "python", title: String? = nil, code: String) {
        self.language = language
        self.title = title
        self.code = code
    }
}

public struct ChartPart: Codable, Equatable, Sendable {
    public enum Kind: String, Codable, Sendable {
        /// x against y, in the order the points came (the robot's path from above).
        case path
        /// A value over time.
        case line
    }

    public struct Series: Codable, Equatable, Sendable {
        public var name: String
        /// `[x, y]` pairs.
        public var points: [[Double]]

        public init(name: String, points: [[Double]]) {
            self.name = name
            self.points = points
        }
    }

    public var title: String
    public var kind: Kind
    public var xLabel: String
    public var yLabel: String
    public var series: [Series]

    public init(title: String, kind: Kind, xLabel: String, yLabel: String, series: [Series]) {
        self.title = title
        self.kind = kind
        self.xLabel = xLabel
        self.yLabel = yLabel
        self.series = series
    }
}

public struct TablePart: Codable, Equatable, Sendable {
    public var title: String?
    public var columns: [String]
    public var rows: [[String]]

    public init(title: String? = nil, columns: [String], rows: [[String]]) {
        self.title = title
        self.columns = columns
        self.rows = rows
    }

    /// The table as CSV, for sharing to Numbers or a spreadsheet.
    public var csv: String {
        func field(_ s: String) -> String {
            s.contains(where: { ",\"\n".contains($0) })
                ? "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\"" : s
        }
        return ([columns] + rows).map { $0.map(field).joined(separator: ",") }
            .joined(separator: "\n") + "\n"
    }
}

/// A piece of a message. Unknown part types from a newer server decode as `.unknown`.
public enum Part: Codable, Equatable, Sendable {
    case text(String)
    case code(CodePart)
    case chart(ChartPart)
    case table(TablePart)
    case unknown(String)

    enum CodingKeys: String, CodingKey { case type, text }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let type = try c.decode(String.self, forKey: .type)
        switch type {
        case "text": self = .text(try c.decode(String.self, forKey: .text))
        case "code": self = .code(try CodePart(from: decoder))
        case "chart": self = .chart(try ChartPart(from: decoder))
        case "table": self = .table(try TablePart(from: decoder))
        default: self = .unknown(type)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .text(let t):
            try c.encode("text", forKey: .type)
            try c.encode(t, forKey: .text)
        case .code(let p):
            try c.encode("code", forKey: .type)
            try p.encode(to: encoder)
        case .chart(let p):
            try c.encode("chart", forKey: .type)
            try p.encode(to: encoder)
        case .table(let p):
            try c.encode("table", forKey: .type)
            try p.encode(to: encoder)
        case .unknown(let type):
            try c.encode(type, forKey: .type)
        }
    }
}

public struct ChatResponse: Codable, Sendable {
    public var conversation: String
    public var messages: [ChatMessage]
}

public struct MessagesResponse: Codable, Sendable {
    public var messages: [ChatMessage]
}

public struct Health: Codable, Equatable, Sendable {
    public var ok: Bool
    public var robot: String?
    public var seconds: Double
    public var maxSpeed: Int
    public var spaceCm: Double?
    public var model: String
}

extension JSONDecoder {
    /// Decodes the server's snake_case JSON.
    public static var server: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}
