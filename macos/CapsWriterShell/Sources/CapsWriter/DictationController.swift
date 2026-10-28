import AppKit
import ApplicationServices
import AVFoundation
import CFNetwork
import CoreGraphics
import Foundation
import CapsWriterCore

// 右 Option 不抑制。录音按 48 kHz 收，每 3 帧取平均后以 16 kHz 单声道送给现在的服务端。
// 只粘贴识别结果里的 text。日志只记事件名。
final class DictationController {
    var note: (String) -> Void = { _ in }
    var settings: () -> ClientSettings = { ClientSettings() }
    var onStatus: (String) -> Void = { _ in }

    private let queue = DispatchQueue(label: "offline.capswriter.dictation")
    private let socket = MicSocket()
    private var globalMonitor: Any?
    private var localMonitor: Any?
    private var engine: AVAudioEngine?
    private var engineReady = false
    private var channelCount = 0
    private var sampleRate = 0.0
    private var holding = false
    private var recording = false
    private var started = Date()
    private var threshold = 0.3
    private var activeSettings = ClientSettings()
    private var taskID = ""
    private var pending: [Float] = []
    private var peak: Float = 0
    private var linkToken = 0
    private var linkOpen = false
    private var handshakeDone = false
    private var handshakeWatch: DispatchWorkItem?
    private var pumping = false
    private var outbound: [String] = []
    private var pendings: [String: PendingTake] = [:]
    private var listenNoted = false

    func startMonitoring() {
        installMonitors()
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            startEngine()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] allowed in
                DispatchQueue.main.async {
                    if allowed {
                        self?.startEngine()
                    } else {
                        self?.onStatus("没有麦克风权限")
                        self?.note("dictation denied")
                    }
                }
            }
        default:
            onStatus("没有麦克风权限")
            note("dictation denied")
        }
    }

    private func installMonitors() {
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
            self?.handle(event)
        }
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
            self?.handle(event)
            return event
        }
        if globalMonitor == nil && !listenNoted {
            listenNoted = true
            onStatus("没有输入监控权限")
            note("listen denied")
        }
    }

    private func startEngine() {
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0, format.commonFormat == .pcmFormatFloat32 else {
            onStatus("麦克风没打开")
            note("dictation mic failed")
            return
        }
        input.installTap(onBus: 0, bufferSize: 2400, format: format) { [weak self] buffer, _ in
            self?.capture(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            onStatus("麦克风没打开")
            note("dictation mic failed")
            return
        }
        self.engine = engine
        let channels = Int(format.channelCount)
        let rate = format.sampleRate
        queue.async {
            self.channelCount = channels
            self.sampleRate = rate
            self.engineReady = true
        }
        socket.onText = { [weak self] text in
            self?.queue.async { self?.handleIncoming(text) }
        }
        socket.onFailure = { [weak self] token in
            self?.queue.async { self?.handleFailure(token) }
        }
    }

    private func handle(_ event: NSEvent) {
        guard event.keyCode == rightOptionKeyCode else { return }
        // 0x40 是右 Option，0x20 是左 Option。系统没给设备位时，这个事件本身就是右 Option。
        let raw = event.modifierFlags.rawValue
        let down: Bool
        if raw & 0x60 != 0 {
            down = raw & 0x40 != 0
        } else {
            down = event.modifierFlags.contains(.option)
        }
        queue.async { self.setHolding(down) }
    }

    private func setHolding(_ down: Bool) {
        if down && !holding {
            holding = true
            begin()
        } else if !down && holding {
            holding = false
            finish()
        }
    }

    private func begin() {
        activeSettings = settings()
        threshold = activeSettings.threshold
        started = Date()
        taskID = UUID().uuidString
        pending.removeAll(keepingCapacity: true)
        peak = 0
        recording = engineReady
        if !engineReady {
            DispatchQueue.main.async {
                self.onStatus("麦克风没打开")
                self.note("dictation mic failed")
            }
        }
    }

    private func capture(_ buffer: AVAudioPCMBuffer) {
        let samples = interleavedFloats(buffer)
        guard !samples.isEmpty else { return }
        queue.async { self.absorb(samples) }
    }

    private func absorb(_ samples: [Float]) {
        guard recording else { return }
        for sample in samples {
            peak = max(peak, abs(sample))
        }
        pending.append(contentsOf: samples)
        guard Date().timeIntervalSince(started) >= threshold else { return }
        let chunk = pending
        pending.removeAll(keepingCapacity: true)
        if !chunk.isEmpty {
            send(chunk, isFinal: false)
        }
    }

    private func finish() {
        recording = false
        let duration = Date().timeIntervalSince(started)
        let capturedPeak = peak
        let tail = pending
        pending.removeAll(keepingCapacity: true)
        if !engineReady {
            return
        }
        if duration < threshold {
            deliver(.short, text: nil)
            return
        }
        let silent = capturedPeak < silencePeak
        if !tail.isEmpty {
            send(tail, isFinal: false)
        }
        register(duration: duration, peak: capturedPeak, silent: silent)
        send([], isFinal: true)
        if silent {
            deliver(.silent, text: nil)
        }
    }

    private func send(_ samples: [Float], isFinal: Bool) {
        let down = toRecognitionRate(samples, channels: channelCount, sampleRate: sampleRate)
        let json = audioMessageJSON(
            taskID: taskID,
            samples: down,
            isFinal: isFinal,
            timeStart: started.timeIntervalSince1970,
            segmentDuration: activeSettings.segmentDuration,
            segmentOverlap: activeSettings.segmentOverlap,
            context: activeSettings.context,
            language: activeSettings.language
        )
        outbound.append(json)
        ensureLink()
        pump()
    }

    private func register(duration: Double, peak: Float, silent: Bool) {
        let id = taskID
        let work = DispatchWorkItem { [weak self] in
            self?.queue.async { self?.expire(id) }
        }
        pendings[id] = PendingTake(
            settings: activeSettings,
            duration: duration,
            peak: peak,
            silent: silent,
            timeout: work
        )
        queue.asyncAfter(deadline: .now() + 60, execute: work)
    }

    private func ensureLink() {
        let wanted = "ws://\(activeSettings.addr):\(activeSettings.port)"
        if linkOpen { return }
        guard let url = URL(string: wanted) else {
            handleFailure(linkToken)
            return
        }
        linkToken = socket.connect(url)
        linkOpen = true
        handshakeDone = false
        handshakeWatch?.cancel()
        let token = linkToken
        let watch = DispatchWorkItem { [weak self] in
            self?.queue.async {
                guard let self, self.linkToken == token, !self.handshakeDone else { return }
                self.handleFailure(token)
            }
        }
        handshakeWatch = watch
        queue.asyncAfter(deadline: .now() + 8, execute: watch)
    }

    private func pump() {
        guard linkOpen, !pumping, !outbound.isEmpty else { return }
        pumping = true
        let text = outbound.removeFirst()
        let token = linkToken
        socket.send(text, token: token) { [weak self] ok in
            self?.queue.async {
                guard let self else { return }
                self.pumping = false
                guard self.linkToken == token, self.linkOpen else { return }
                if !ok {
                    self.handleFailure(token)
                    return
                }
                self.handshakeDone = true
                self.handshakeWatch?.cancel()
                self.pump()
            }
        }
    }

    private func handleIncoming(_ text: String) {
        guard let parsed = recognitionText(from: text), parsed.isFinal else { return }
        guard let item = pendings.removeValue(forKey: parsed.taskID) else { return }
        item.timeout.cancel()
        if item.silent { return }
        let stripped = stripTrailingPunctuation(
            parsed.text,
            marks: item.settings.trashPunctuation,
            threshold: item.settings.trashThreshold
        )
        let outcome = classifyDictation(
            duration: item.duration,
            threshold: item.settings.threshold,
            peak: item.peak,
            text: stripped
        )
        if outcome == .text {
            deliver(.text, text: stripped)
        } else {
            deliver(.empty, text: nil)
        }
    }

    private func expire(_ id: String) {
        guard let item = pendings.removeValue(forKey: id) else { return }
        if item.silent { return }
        deliver(.empty, text: nil)
    }

    private func handleFailure(_ token: Int) {
        guard token == linkToken, linkOpen else { return }
        linkOpen = false
        handshakeWatch?.cancel()
        pumping = false
        outbound.removeAll()
        recording = false
        holding = false
        pending.removeAll(keepingCapacity: true)
        let waiting = pendings
        pendings.removeAll()
        for item in waiting.values {
            item.timeout.cancel()
        }
        let onlySilent = !waiting.isEmpty && waiting.values.allSatisfy { $0.silent }
        if !onlySilent {
            DispatchQueue.main.async {
                self.onStatus("服务端没连上")
                self.note("dictation disconnected")
            }
        }
    }

    private func deliver(_ outcome: DictationOutcome, text: String?) {
        DispatchQueue.main.async {
            switch outcome {
            case .short:
                self.onStatus(dictationStatus(.short))
                self.note("dictation short")
            case .silent:
                self.onStatus(dictationStatus(.silent))
                self.note("dictation silent")
            case .empty:
                self.onStatus(dictationStatus(.empty))
                self.note("dictation empty")
            case .text:
                if self.paste(text ?? "") {
                    self.onStatus(dictationStatus(.text))
                    self.note("dictation finished")
                    self.note("paste posted")
                } else {
                    self.onStatus("没有辅助功能权限")
                    self.note("paste failed")
                }
            }
        }
    }

    private func paste(_ text: String) -> Bool {
        guard !text.isEmpty else { return false }
        let board = NSPasteboard.general
        let original = board.string(forType: .string)
        board.clearContents()
        guard board.setString(text, forType: .string) else { return false }
        guard AXIsProcessTrusted(), postCommandV() else { return false }
        if let original, !original.isEmpty {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                board.clearContents()
                board.setString(original, forType: .string)
            }
        }
        return true
    }

    private func postCommandV() -> Bool {
        let source = CGEventSource(stateID: .hidSystemState)
        guard let down = CGEvent(keyboardEventSource: source, virtualKey: 0x09, keyDown: true),
              let up = CGEvent(keyboardEventSource: source, virtualKey: 0x09, keyDown: false) else {
            return false
        }
        down.flags = .maskCommand
        up.flags = .maskCommand
        down.post(tap: .cghidEventTap)
        up.post(tap: .cghidEventTap)
        return true
    }

    private func interleavedFloats(_ buffer: AVAudioPCMBuffer) -> [Float] {
        let frames = Int(buffer.frameLength)
        let channels = Int(buffer.format.channelCount)
        guard frames > 0, channels > 0, let data = buffer.floatChannelData else { return [] }
        if buffer.format.isInterleaved {
            return Array(UnsafeBufferPointer(start: data[0], count: frames * channels))
        }
        var output: [Float] = []
        output.reserveCapacity(frames * channels)
        for frame in 0..<frames {
            for channel in 0..<channels {
                output.append(data[channel][frame])
            }
        }
        return output
    }
}

private struct PendingTake {
    var settings: ClientSettings
    var duration: Double
    var peak: Float
    var silent: Bool
    var timeout: DispatchWorkItem
}

private final class MicSocket {
    var onText: (String) -> Void = { _ in }
    var onFailure: (Int) -> Void = { _ in }

    private let lock = NSLock()
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var generation = 0

    init() {
        let config = URLSessionConfiguration.ephemeral
        config.waitsForConnectivity = false
        config.connectionProxyDictionary = [
            kCFNetworkProxiesHTTPEnable: 0,
            kCFNetworkProxiesHTTPSEnable: 0,
            kCFNetworkProxiesSOCKSEnable: 0,
        ]
        session = URLSession(configuration: config)
    }

    func connect(_ url: URL) -> Int {
        lock.lock()
        generation += 1
        let token = generation
        task?.cancel(with: .goingAway, reason: nil)
        let next = session.webSocketTask(with: url, protocols: ["binary"])
        next.maximumMessageSize = 8_000_000
        task = next
        lock.unlock()
        next.resume()
        listen(token)
        return token
    }

    func send(_ text: String, token: Int, done: @escaping (Bool) -> Void) {
        lock.lock()
        let current = generation
        let socket = task
        lock.unlock()
        guard token == current, let socket else {
            done(false)
            return
        }
        socket.send(.string(text)) { [weak self] error in
            guard let self else {
                done(false)
                return
            }
            self.lock.lock()
            let matches = token == self.generation
            self.lock.unlock()
            done(error == nil && matches)
        }
    }

    private func listen(_ token: Int) {
        lock.lock()
        let socket = task
        let matches = token == generation
        lock.unlock()
        guard matches, let socket else { return }
        socket.receive { [weak self] result in
            guard let self else { return }
            self.lock.lock()
            let current = self.generation == token
            self.lock.unlock()
            guard current else { return }
            switch result {
            case .success(let message):
                if let text = Self.text(from: message) {
                    self.onText(text)
                }
                self.listen(token)
            case .failure:
                self.onFailure(token)
            }
        }
    }

    private static func text(from message: URLSessionWebSocketTask.Message) -> String? {
        switch message {
        case .string(let value):
            return value
        case .data(let data):
            return String(data: data, encoding: .utf8)
        @unknown default:
            return nil
        }
    }
}
