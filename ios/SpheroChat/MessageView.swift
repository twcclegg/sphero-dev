import SpheroChatCore
import SwiftUI
import UIKit

struct MessageView: View {
    let message: ChatMessage
    /// Show Run / Export under this message (it holds the latest program).
    let isLatestProgram: Bool

    var body: some View {
        switch message.role {
        case .user:
            HStack {
                Spacer(minLength: 60)
                Text(plainText)
                    .textSelection(.enabled)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 18).fill(Color.accentColor.opacity(0.15)))
            }
        case .status:
            Label(plainText, systemImage: "gearshape.2")
                .font(.caption)
                .foregroundStyle(.secondary)
        case .error:
            Label(plainText, systemImage: "exclamationmark.triangle")
                .font(.callout)
                .foregroundStyle(.red)
        case .assistant:
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(displayParts.enumerated()), id: \.offset) { _, part in
                    PartView(part: part)
                }
                if isLatestProgram {
                    ProgramActions()
                }
            }
        }
    }

    private var plainText: String {
        var lines: [String] = []
        for case .text(let t) in message.parts { lines.append(t) }
        return lines.joined(separator: "\n")
    }

    /// Text parts with ``` fences become code blocks.
    private var displayParts: [Part] {
        var out: [Part] = []
        for part in message.parts {
            if case .text(let t) = part {
                out += Markdown.split(t)
            } else {
                out.append(part)
            }
        }
        return out
    }
}

struct PartView: View {
    let part: Part

    var body: some View {
        switch part {
        case .text(let t):
            Text(markdown(t))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .code(let c):
            CodeBlockView(part: c)
        case .chart(let c):
            ChartPartView(part: c)
        case .table(let t):
            TablePartView(part: t)
        case .unknown:
            EmptyView()
        }
    }

    private func markdown(_ t: String) -> AttributedString {
        (try? AttributedString(
            markdown: t,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(t)
    }
}

/// Run the latest program on the robot, or export it for the Sphero Edu app.
struct ProgramActions: View {
    @Environment(ChatStore.self) private var store
    @State private var share: ShareItem?
    @State private var exportError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 12) {
                if store.activity == .running {
                    Button(role: .destructive) {
                        Task { await store.stop() }
                    } label: {
                        Label("Stop", systemImage: "stop.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                } else {
                    Button {
                        Task { await store.run() }
                    } label: {
                        Label("Run on robot", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(store.activity != .idle)
                }
                Button {
                    Task {
                        do {
                            share = ShareItem(url: try await store.labFile())
                            exportError = nil
                        } catch {
                            exportError = error.localizedDescription
                        }
                    }
                } label: {
                    Label("Export .lab", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.bordered)
            }
            if let exportError {
                Text(exportError).font(.caption).foregroundStyle(.red)
            }
        }
        .sheet(item: $share) { item in
            ShareSheet(items: [item.url])
        }
    }
}

struct ShareItem: Identifiable {
    let url: URL
    var id: URL { url }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
