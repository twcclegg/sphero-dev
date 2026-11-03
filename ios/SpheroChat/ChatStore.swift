import Foundation
import Observation
import SpheroChatCore

/// The conversation, the connection settings, and what's in progress.
@MainActor @Observable
final class ChatStore {
    enum Activity: Equatable { case idle, thinking, running }

    var messages: [ChatMessage] = []
    var conversation: String?
    var activity: Activity = .idle
    var address: String { didSet { UserDefaults.standard.set(address, forKey: "address") } }
    var token: String { didSet { UserDefaults.standard.set(token, forKey: "token") } }

    var server: SpheroServer? { SpheroServer(address: address, token: token) }

    /// The message holding the program a Run would run: the latest one with code.
    var latestProgramID: UUID? { messages.last(where: { $0.code != nil })?.id }

    private struct Saved: Codable {
        var conversation: String?
        var messages: [ChatMessage]
    }

    private static var historyURL: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("history.json")
    }

    init() {
        address = UserDefaults.standard.string(forKey: "address") ?? ""
        token = UserDefaults.standard.string(forKey: "token") ?? ""
        if let data = try? Data(contentsOf: Self.historyURL),
           let saved = try? JSONDecoder().decode(Saved.self, from: data) {
            messages = saved.messages
            conversation = saved.conversation
        }
    }

    func send(_ raw: String) async {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, activity == .idle else { return }
        guard let server else {
            append(.text(.error, "Set the server address and token in Settings first."))
            return
        }
        append(.text(.user, text))
        activity = .thinking
        defer {
            activity = .idle
            save()
        }
        do {
            let reply: ChatResponse
            do {
                reply = try await server.chat(conversation: conversation, text: text)
            } catch let e as ServerError where e.status == 404 && conversation != nil {
                // The server keeps conversations in memory; it was restarted.
                conversation = nil
                append(.text(.status, "The server was restarted, so Claude starts afresh and "
                             + "won't remember the messages above."))
                reply = try await server.chat(conversation: nil, text: text)
            }
            conversation = reply.conversation
            messages += reply.messages
        } catch {
            append(.text(.error, describe(error)))
        }
    }

    func run() async {
        guard activity == .idle, let server else { return }
        guard let conversation else {
            append(.text(.error, "The server doesn't have this program any more (it was "
                         + "restarted). Ask for it again."))
            return
        }
        activity = .running
        defer {
            activity = .idle
            save()
        }
        do {
            messages += try await server.run(conversation: conversation)
        } catch {
            append(.text(.error, describe(error)))
        }
    }

    func stop() async {
        do {
            try await server?.stop()
        } catch {
            append(.text(.error, "Couldn't send stop: \(describe(error))"))
        }
    }

    /// Downloads the latest program as a `.lab` file for the Sphero Edu app's Import.
    func labFile() async throws -> URL {
        guard let server, let conversation else {
            throw ServerError(status: 404, message: "The server doesn't have this program any more.")
        }
        let (name, data) = try await server.programLab(conversation: conversation)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        try data.write(to: url, options: .atomic)
        return url
    }

    func newConversation() {
        guard activity == .idle else { return }
        messages = []
        conversation = nil
        save()
    }

    private func append(_ m: ChatMessage) {
        messages.append(m)
    }

    private func save() {
        let saved = Saved(conversation: conversation, messages: messages)
        if let data = try? JSONEncoder().encode(saved) {
            try? data.write(to: Self.historyURL, options: .atomic)
        }
    }

    private func describe(_ error: Error) -> String {
        if let e = error as? ServerError {
            return e.status == 401 ? "The server rejected the token. Check it in Settings."
                                   : e.message
        }
        if let e = error as? URLError {
            switch e.code {
            case .cannotConnectToHost, .cannotFindHost, .timedOut, .networkConnectionLost,
                 .notConnectedToInternet:
                return "Couldn't reach the server at \(address). Is `sphero-dev serve` running, "
                    + "and is this iPad on the same Wi-Fi? (\(e.localizedDescription))"
            default:
                break
            }
        }
        return error.localizedDescription
    }
}
