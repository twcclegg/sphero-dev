import SpheroChatCore
import SwiftUI
import UIKit

@main
struct SpheroChatApp: App {
    @State private var store = ChatStore()

    var body: some Scene {
        WindowGroup {
            ChatView()
                .environment(store)
        }
    }
}

struct ChatView: View {
    @Environment(ChatStore.self) private var store
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        if store.messages.isEmpty {
                            EmptyStateView()
                        }
                        ForEach(store.messages) { message in
                            MessageView(message: message,
                                        isLatestProgram: message.id == store.latestProgramID)
                                .id(message.id)
                        }
                        if store.activity != .idle {
                            ActivityRow(activity: store.activity)
                                .id("activity")
                        }
                    }
                    .padding()
                    .frame(maxWidth: 860)
                    .frame(maxWidth: .infinity)
                }
                .scrollDismissesKeyboard(.interactively)
                .defaultScrollAnchor(.bottom)
                .onChange(of: store.messages.count) {
                    if let last = store.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
                .onChange(of: store.activity) {
                    if store.activity != .idle {
                        withAnimation { proxy.scrollTo("activity", anchor: .bottom) }
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                InputBar()
            }
            .navigationTitle("Sphero")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        Task { await store.newConversation() }
                    } label: {
                        Label("New conversation", systemImage: "square.and.pencil")
                    }
                    .disabled(store.activity != .idle || store.messages.isEmpty)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Label("Settings", systemImage: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
        .onAppear {
            if store.apiKey.isEmpty { showSettings = true }
        }
    }
}

struct EmptyStateView: View {
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "circle.circle")
                .font(.system(size: 44))
                .foregroundStyle(.tint)
            Text("What should the robot do?")
                .font(.title3.weight(.semibold))
            Text("Try “drive a square, 50 cm a side, green on the corners”. Claude writes "
                 + "the program and checks it in the simulator; you choose whether to run it.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: 460)
        .frame(maxWidth: .infinity)
        .padding(.top, 80)
    }
}

struct ActivityRow: View {
    let activity: ChatStore.Activity

    var body: some View {
        HStack(spacing: 10) {
            ProgressView()
            Text(activity == .running ? "Running on the robot…"
                                      : "Claude is writing and simulating the program…")
                .foregroundStyle(.secondary)
        }
        .font(.callout)
    }
}

/// The text box, the microphone and send (or stop, while the robot runs).
struct InputBar: View {
    @Environment(ChatStore.self) private var store
    @State private var draft = ""
    @State private var speech = SpeechRecognizer()
    @State private var beforeDictation = ""
    @FocusState private var focused: Bool

    private var canSend: Bool {
        store.activity == .idle && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 6) {
            if let error = speech.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            HStack(alignment: .bottom, spacing: 10) {
                TextField(speech.isRecording ? "Listening…" : "Describe what the robot should do",
                          text: $draft, axis: .vertical)
                    .lineLimit(1...8)
                    .focused($focused)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 20).fill(Color(.secondarySystemBackground)))
                    .onSubmit(send)

                Button {
                    if !speech.isRecording { beforeDictation = draft }
                    Task { await speech.toggle() }
                } label: {
                    Image(systemName: speech.isRecording ? "waveform.circle.fill" : "mic.circle")
                        .font(.system(size: 34))
                        .symbolEffect(.pulse, isActive: speech.isRecording)
                        .foregroundStyle(speech.isRecording ? Color.red : Color.secondary)
                }
                .accessibilityLabel(speech.isRecording ? "Stop dictation" : "Dictate")

                if store.activity == .running {
                    Button {
                        Task { await store.stop() }
                    } label: {
                        Image(systemName: "stop.circle.fill")
                            .font(.system(size: 34))
                            .foregroundStyle(.red)
                    }
                    .accessibilityLabel("Stop the robot")
                } else {
                    Button(action: send) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 34))
                    }
                    .disabled(!canSend)
                    .accessibilityLabel("Send")
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .frame(maxWidth: 860)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .onChange(of: speech.transcript) {
            let sep = beforeDictation.isEmpty || beforeDictation.hasSuffix(" ") ? "" : " "
            draft = beforeDictation + sep + speech.transcript
        }
    }

    private func send() {
        guard canSend else { return }
        if speech.isRecording { speech.stop() }
        let text = draft
        draft = ""
        beforeDictation = ""
        Task { await store.send(text) }
    }
}
