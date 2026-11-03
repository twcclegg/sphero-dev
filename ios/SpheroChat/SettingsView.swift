import SwiftUI

struct SettingsView: View {
    @Environment(ChatStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var scanning = false
    @State private var found: [String] = []
    @State private var scanMessage: String?

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section {
                    SecureField("sk-ant-…", text: $store.apiKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Picker("Model", selection: $store.model) {
                        ForEach(ChatStore.models, id: \.self) { Text($0) }
                    }
                } header: {
                    Text("Claude")
                } footer: {
                    Text("An API key from console.anthropic.com. It's kept in this iPad's "
                         + "Keychain and sent only to Anthropic. Requests are billed to that "
                         + "account.")
                }

                Section {
                    TextField("First robot found", text: $store.robotName)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                    Button {
                        Task { await scan() }
                    } label: {
                        HStack {
                            Text("Find robots")
                            if scanning {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(scanning)
                    ForEach(found, id: \.self) { name in
                        Button {
                            store.robotName = name
                        } label: {
                            Label(name, systemImage: store.robotName == name
                                  ? "checkmark.circle.fill" : "circle")
                        }
                    }
                    if let scanMessage {
                        Text(scanMessage).font(.callout).foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Robot")
                } footer: {
                    Text("BOLT+ names start with BP-, BOLT with SB-. Shake or tap the robot to "
                         + "wake it, and close the Sphero Edu app so it isn't connected.")
                }

                Section {
                    Stepper("Top speed: \(store.maxSpeed)", value: $store.maxSpeed,
                            in: 40...255, step: 10)
                    Stepper("Stop after \(store.seconds) s", value: $store.seconds,
                            in: 5...120, step: 5)
                    Stepper(store.spaceCm == 0 ? "Floor space: not stated"
                                               : "Floor space: \(store.spaceCm) cm",
                            value: $store.spaceCm, in: 0...500, step: 10)
                } header: {
                    Text("Limits")
                } footer: {
                    Text("Every run is capped at this speed (0-255) and stopped after this "
                         + "long. Floor space is the clear floor around the robot's start; "
                         + "Claude keeps the path inside it (about 1.5 m if not stated).")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func scan() async {
        scanning = true
        scanMessage = nil
        defer { scanning = false }
        let names: [String] = await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let list = (try? BluetoothBridge.shared.scan(timeout: 4)) ?? []
                let sphero = list.compactMap { $0["name"] }
                    .filter { name in ["BP-", "SB-", "SM-", "SK-"].contains { name.hasPrefix($0) } }
                cont.resume(returning: Array(Set(sphero)).sorted())
            }
        }
        found = names
        if names.isEmpty {
            scanMessage = "No Sphero robots found. Is Bluetooth on, and is the robot awake?"
        }
    }
}
