import SpheroChatCore
import SwiftUI

struct SettingsView: View {
    @Environment(ChatStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var checking = false
    @State private var result: String?
    @State private var ok = false

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section {
                    TextField("sphero.clegg.dev", text: $store.address)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Token", text: $store.token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Server")
                } footer: {
                    Text("On the computer next to the robot, run `sphero-dev serve`. It prints "
                         + "the address and token to enter here. The iPad and the computer must "
                         + "be on the same Wi-Fi.")
                }
                Section {
                    Button {
                        Task { await check() }
                    } label: {
                        HStack {
                            Text("Test connection")
                            if checking {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(checking || store.server == nil)
                    if let result {
                        Label(result, systemImage: ok ? "checkmark.circle" : "xmark.circle")
                            .foregroundStyle(ok ? .green : .red)
                            .font(.callout)
                    }
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

    private func check() async {
        guard let server = store.server else { return }
        checking = true
        defer { checking = false }
        do {
            let h = try await server.health()
            ok = true
            var parts = ["Connected. Robot: \(h.robot ?? "first one found")",
                         "max speed \(h.maxSpeed)", "\(Int(h.seconds)) s per run"]
            if let space = h.spaceCm { parts.append("\(Int(space)) cm of floor") }
            result = parts.joined(separator: ", ") + "."
        } catch let e as ServerError where e.status == 401 {
            ok = false
            result = "The server rejected the token."
        } catch {
            ok = false
            result = error.localizedDescription
        }
    }
}
