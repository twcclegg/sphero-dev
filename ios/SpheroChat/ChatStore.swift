import Foundation
import Observation
import SpheroChatCore

/// The conversation, the settings, and what's in progress. Claude, the
/// simulator and the robot all run in the app's embedded Python
/// (`sphero_dev.app`); this keeps the history and the settings.
@MainActor @Observable
final class ChatStore {
    enum Activity: Equatable { case idle, thinking, running }

    static let models = ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]

    var messages: [ChatMessage] = []
    var activity: Activity = .idle

    // Settings. The API key lives in the Keychain, the rest in UserDefaults.
    var apiKey: String { didSet { Keychain.set("anthropic-api-key", apiKey) } }
    var robotName: String { didSet { defaults.set(robotName, forKey: "robot") } }
    var maxSpeed: Int { didSet { defaults.set(maxSpeed, forKey: "maxSpeed") } }
    var seconds: Int { didSet { defaults.set(seconds, forKey: "seconds") } }
    /// Clear floor around the start, cm; 0 = not stated (Claude assumes about 1.5 m).
    var spaceCm: Int { didSet { defaults.set(spaceCm, forKey: "spaceCm") } }
    var model: String { didSet { defaults.set(model, forKey: "model") } }

    /// The message holding the program a Run would run: the latest one with code.
    var latestProgramID: UUID? { messages.last(where: { $0.code != nil })?.id }

    private let defaults = UserDefaults.standard
    /// Python's conversation starts empty each launch; say so once if there's history.
    private var claudeRemembers = false

    private static var historyURL: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("history.json")
    }

    init() {
        apiKey = Keychain.get("anthropic-api-key") ?? ""
        robotName = defaults.string(forKey: "robot") ?? ""
        maxSpeed = defaults.object(forKey: "maxSpeed") as? Int ?? 150
        seconds = defaults.object(forKey: "seconds") as? Int ?? 30
        spaceCm = defaults.object(forKey: "spaceCm") as? Int ?? 0
        model = defaults.string(forKey: "model") ?? Self.models[0]
        if let data = try? Data(contentsOf: Self.historyURL),
           let saved = try? JSONDecoder().decode([ChatMessage].self, from: data) {
            messages = saved
        }
    }

    /// Hand the settings to Python. Called before each request, so edits apply at once.
    private func configure() async {
        let settings: [String: Any] = [
            "api_key": apiKey, "model": model, "robot": robotName,
            "seconds": seconds, "max_speed": maxSpeed,
            "space_cm": spaceCm > 0 ? spaceCm : NSNull(),
        ]
        let data = (try? JSONSerialization.data(withJSONObject: settings)) ?? Data("{}".utf8)
        _ = await PythonRuntime.call("configure", String(decoding: data, as: UTF8.self))
    }

    func send(_ raw: String) async {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, activity == .idle else { return }
        if !claudeRemembers && !messages.isEmpty {
            append(.text(.status, "Claude starts afresh each time the app opens, so it won't "
                         + "remember the messages above."))
        }
        claudeRemembers = true
        append(.text(.user, text))
        activity = .thinking
        defer {
            activity = .idle
            save()
        }
        await configure()
        messages += decode(await PythonRuntime.call("chat", text))
    }

    func run() async {
        guard activity == .idle else { return }
        activity = .running
        defer {
            activity = .idle
            save()
        }
        await configure()
        messages += decode(await PythonRuntime.call("run"))
    }

    func stop() async {
        _ = await PythonRuntime.call("stop")
    }

    /// The latest program as a `.lab` file, for the Sphero Edu app's Import.
    func labFile() async throws -> URL {
        struct LabFile: Decodable { var name: String?; var content: String? }
        let json = await PythonRuntime.call("lab_file")
        let f = try JSONDecoder().decode(LabFile.self, from: Data(json.utf8))
        guard let name = f.name, let content = f.content else {
            throw CocoaError(.fileNoSuchFile, userInfo: [
                NSLocalizedDescriptionKey: "Claude doesn't have this program any more (the app "
                    + "restarted). Ask for it again."])
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        try Data(content.utf8).write(to: url, options: .atomic)
        return url
    }

    func newConversation() async {
        guard activity == .idle else { return }
        messages = []
        save()
        _ = await PythonRuntime.call("new_conversation")
    }

    private func decode(_ json: String) -> [ChatMessage] {
        struct Reply: Decodable { var messages: [ChatMessage]? }
        do {
            return try JSONDecoder.snakeCase.decode(Reply.self, from: Data(json.utf8)).messages ?? []
        } catch {
            return [.text(.error, "Couldn't read the reply: \(error.localizedDescription)")]
        }
    }

    private func append(_ m: ChatMessage) {
        messages.append(m)
    }

    private func save() {
        if let data = try? JSONEncoder().encode(messages) {
            try? data.write(to: Self.historyURL, options: .atomic)
        }
    }
}
