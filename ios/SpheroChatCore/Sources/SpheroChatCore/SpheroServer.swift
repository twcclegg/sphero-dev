@preconcurrency import Foundation
#if canImport(FoundationNetworking)
@preconcurrency import FoundationNetworking
#endif

public struct ServerError: LocalizedError, Equatable {
    public var status: Int
    public var message: String
    public var errorDescription: String? { message }
}

/// Talks to `sphero-dev serve` on the computer next to the robot.
public struct SpheroServer: Sendable {
    public var baseURL: URL
    public var token: String

    public init(baseURL: URL, token: String) {
        self.baseURL = baseURL
        self.token = token
    }

    /// Accepts "192.168.1.20", "192.168.1.20:8765" or a full URL.
    public init?(address: String, token: String) {
        var s = address.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return nil }
        if !s.contains("://") { s = "http://" + s }
        guard var parts = URLComponents(string: s), parts.host?.isEmpty == false else { return nil }
        if parts.port == nil { parts.port = 8765 }
        guard let url = parts.url else { return nil }
        self.init(baseURL: url, token: token.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    public func health() async throws -> Health {
        try await request("GET", "health", body: nil, timeout: 10)
    }

    /// Claude can take a minute or two (it simulates its drafts), hence the long timeout.
    public func chat(conversation: String?, text: String) async throws -> ChatResponse {
        var body: [String: String] = ["text": text]
        if let conversation { body["conversation"] = conversation }
        return try await request("POST", "chat", body: body, timeout: 600)
    }

    /// Runs the conversation's latest program on the robot; returns when it's done.
    public func run(conversation: String) async throws -> [ChatMessage] {
        let r: MessagesResponse = try await request(
            "POST", "run", body: ["conversation": conversation], timeout: 300)
        return r.messages
    }

    public func stop() async throws {
        struct Stopping: Decodable { var stopping: Bool }
        let _: Stopping = try await request("POST", "stop", body: [String: String](), timeout: 10)
    }

    /// The latest program as a Sphero Edu `.lab` file: (file name, contents).
    public func programLab(conversation: String) async throws -> (String, Data) {
        var parts = URLComponents(url: baseURL.appendingPathComponent("program.lab"),
                                  resolvingAgainstBaseURL: false)!
        parts.queryItems = [URLQueryItem(name: "conversation", value: conversation)]
        var req = URLRequest(url: parts.url!, timeoutInterval: 30)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await fetch(req)
        try check(response, data)
        let disposition = (response as? HTTPURLResponse)?
            .value(forHTTPHeaderField: "Content-Disposition") ?? ""
        let name = disposition.components(separatedBy: "filename=\"").dropFirst().first?
            .components(separatedBy: "\"").first ?? "program.lab"
        return (name, data)
    }

    func request<T: Decodable>(_ method: String, _ path: String, body: [String: String]?,
                               timeout: TimeInterval) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path), timeoutInterval: timeout)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONEncoder().encode(body)
        }
        let (data, response) = try await fetch(req)
        try check(response, data)
        return try JSONDecoder.server.decode(T.self, from: data)
    }

    /// `URLSession.data(for:)`, which Linux's Foundation lacks.
    private func fetch(_ req: URLRequest) async throws -> (Data, URLResponse) {
        try await withCheckedThrowingContinuation { cont in
            URLSession.shared.dataTask(with: req) { data, response, error in
                if let error {
                    cont.resume(throwing: error)
                } else {
                    cont.resume(returning: (data ?? Data(), response!))
                }
            }.resume()
        }
    }

    private func check(_ response: URLResponse, _ data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            struct Err: Decodable { var error: String }
            let message = (try? JSONDecoder().decode(Err.self, from: data))?.error
                ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            throw ServerError(status: http.statusCode, message: message)
        }
    }
}
