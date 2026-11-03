import AVFoundation
import Observation
import Speech

/// Live dictation into the input box, using Apple's speech recognizer
/// (on the device when it supports that).
@MainActor @Observable
final class SpeechRecognizer {
    private(set) var transcript = ""
    private(set) var isRecording = false
    var error: String?

    private var engine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    func toggle() async {
        if isRecording { stop() } else { await start() }
    }

    func start() async {
        error = nil
        transcript = ""
        guard await Self.authorize() else {
            error = "To dictate, allow Microphone and Speech Recognition for this app in Settings."
            return
        }
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else {
            error = "Speech recognition isn't available right now."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let engine = AVAudioEngine()
            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            if recognizer.supportsOnDeviceRecognition {
                request.requiresOnDeviceRecognition = true
            }
            Self.feed(engine.inputNode, to: request)
            engine.prepare()
            try engine.start()
            self.engine = engine
            self.request = request
            task = Self.recognize(recognizer, request) { [weak self] text, done in
                Task { @MainActor in
                    guard let self else { return }
                    if let text { self.transcript = text }
                    if done { self.finish() }
                }
            }
            isRecording = true
        } catch {
            self.error = "Couldn't start the microphone: \(error.localizedDescription)"
            finish()
        }
    }

    /// Stop listening; the last words still come through as the final result.
    func stop() {
        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        engine = nil
        request = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func finish() {
        stop()
        task = nil
    }

    // The audio tap and recognition callbacks run off the main thread, so they're
    // set up outside the main actor.

    nonisolated private static func feed(_ input: AVAudioInputNode,
                                         to request: SFSpeechAudioBufferRecognitionRequest) {
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) {
            buffer, _ in request.append(buffer)
        }
    }

    nonisolated private static func recognize(
        _ recognizer: SFSpeechRecognizer, _ request: SFSpeechAudioBufferRecognitionRequest,
        update: @escaping @Sendable (String?, Bool) -> Void
    ) -> SFSpeechRecognitionTask {
        recognizer.recognitionTask(with: request) { result, error in
            update(result?.bestTranscription.formattedString,
                   error != nil || (result?.isFinal ?? false))
        }
    }

    nonisolated private static func authorize() async -> Bool {
        let speech = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0 == .authorized) }
        }
        guard speech else { return false }
        return await AVAudioApplication.requestRecordPermission()
    }
}
