import Foundation

/// The embedded Python running `sphero_dev.app`. The build copies the standard
/// library to `python/`, our code to `app/` and its pure-Python packages to
/// `app_packages/` in the app bundle (ios/scripts/install-python.sh).
enum PythonRuntime {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var started = false
    nonisolated(unsafe) private static var startError: String?

    /// Start Python if it isn't yet. Returns why it couldn't, or nil.
    static func start() -> String? {
        lock.lock()
        defer { lock.unlock() }
        if started { return startError }
        started = true
        let bundle = Bundle.main.bundlePath
        let home = bundle + "/python"
        guard let stdlib = try? FileManager.default
            .contentsOfDirectory(atPath: home + "/lib")
            .first(where: { $0.hasPrefix("python3") })
        else {
            startError = "The app was built without Python (no \(home)/lib/python3.x)."
            return startError
        }
        // NUL-separated, double-NUL-terminated list of extra sys.path entries.
        let paths = ContiguousArray(([bundle + "/app", bundle + "/app_packages"]
            .joined(separator: "\0") + "\0").utf8CString)  // utf8CString adds the last NUL
        let stdlibPath = home + "/lib/" + stdlib
        let error = paths.withUnsafeBufferPointer { p in
            sd_python_start(home, stdlibPath, p.baseAddress)
        }
        if let error {
            startError = "Python didn't start: " + String(cString: error)
            free(error)
        }
        // Make sure Bluetooth is set up before Python first asks for it.
        _ = BluetoothBridge.shared
        return startError
    }

    /// Call `sphero_dev.app.<function>(argument)` off the main thread.
    static func call(_ function: String, _ argument: String? = nil) async -> String {
        await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                if let error = start() {
                    cont.resume(returning: errorJSON(error))
                    return
                }
                let raw: UnsafeMutablePointer<CChar>?
                if let argument {
                    raw = sd_python_call(function, argument)
                } else {
                    raw = sd_python_call(function, nil)
                }
                guard let raw else {
                    cont.resume(returning: errorJSON("Python returned nothing."))
                    return
                }
                let out = String(cString: raw)
                free(raw)
                cont.resume(returning: out)
            }
        }
    }

    private static func errorJSON(_ message: String) -> String {
        let obj: [String: Any] = ["messages": [["role": "error",
                                                "parts": [["type": "text", "text": message]]]]]
        let data = (try? JSONSerialization.data(withJSONObject: obj)) ?? Data()
        return String(decoding: data, as: UTF8.self)
    }
}
