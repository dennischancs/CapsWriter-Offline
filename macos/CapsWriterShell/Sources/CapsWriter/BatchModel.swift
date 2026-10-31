import Combine
import Darwin
import Foundation
import CapsWriterCore

enum Lamp {
    case red
    case yellow
    case green
}

@MainActor
final class BatchModel: ObservableObject {
    @Published var target = ""
    @Published var recursive = true
    @Published var splitLong = true
    @Published var force = false
    @Published var hidden = false
    @Published var startServer = true
    @Published var stopServer = false
    @Published var model = "sensevoice"
    @Published var availableModels: [(id: String, label: String)] = modelChoices
    @Published var logLevel = "INFO"
    @Published var lamp: Lamp = .red
    @Published var readyText = "还没准备好"
    @Published var status = "空闲"
    @Published var progressText = "当前 0 / 总计 0"
    @Published var progressValue = 0.0
    @Published var progressTotal = 0
    @Published var ready = false
    @Published var busy = false
    @Published var preparing = false

    let root: String?
    let python: String
    let bundled: Bool
    var note: (String) -> Void = { _ in }
    var onConfigurationChanged: () -> Void = {}

    private var partial = ""
    private var terminalLog = TerminalLog()
    private var batchCount = BatchCount()
    private var logText = ""
    private var logSink: (([LogEdit]) -> Void)?
    private var stopGeneration = 0
    private var prepareProcess: Process?
    private var batchProcess: Process?
    private var stoppedByUser = false
    private var prepareOutput = ""
    private var loadedServerModel = ""
    private var waitingForModelSwitch = false
    private let portWaitLimit = 40

    init() {
        let env = ProcessInfo.processInfo.environment
        python = resolvePython(environment: env["CAPSWRITER_PYTHON"]) { path in
            FileManager.default.isExecutableFile(atPath: path)
        }
        var starts: [String] = []
        if let given = env["CAPSWRITER_ROOT"] { starts.append(given) }
        starts.append(FileManager.default.currentDirectoryPath)
        starts.append(Bundle.main.bundlePath)
        starts.append(CommandLine.arguments.first ?? "")
        if let runtime = preferBundledRuntime(bundlePath: Bundle.main.bundlePath, isRuntime: Self.isRuntime) {
            root = runtime
            bundled = true
        } else {
            bundled = false
            root = findRepositoryRoot(starts: starts) { path in
                let base = URL(fileURLWithPath: path)
                let script = base.appendingPathComponent("batch_transcribe.py").path
                let config = base.appendingPathComponent("config_server.py").path
                return FileManager.default.fileExists(atPath: script)
                    && FileManager.default.fileExists(atPath: config)
            }
        }
        if let root {
            let config = (try? String(contentsOfFile: root + "/config_server.py", encoding: .utf8)) ?? ""
            model = readModelChoice(config, memory: ProcessInfo.processInfo.physicalMemory)
            refreshModels()
        }
    }

    func refreshModels() {
        guard let root else {
            availableModels = []
            return
        }
        let manager = FileManager.default
        let found = installedModelChoices(root: root, isDirectory: { path in
            var isDir: ObjCBool = false
            return manager.fileExists(atPath: path, isDirectory: &isDir) && isDir.boolValue
        }, containsFile: { folder, name in
            if name == "*" {
                guard let names = try? manager.contentsOfDirectory(atPath: folder) else { return false }
                return names.contains { $0.hasSuffix(".onnx") || $0 == "model.safetensors" }
                    || Self.nestedWeights(manager, folder)
            }
            return manager.fileExists(atPath: folder + "/" + name)
        })
        availableModels = found
        if !found.contains(where: { $0.id == model }), let first = found.first {
            model = first.id
        }
    }

    private static func nestedWeights(_ manager: FileManager, _ folder: String) -> Bool {
        guard let items = manager.enumerator(atPath: folder) else { return false }
        for case let name as String in items {
            if name.hasSuffix("model.safetensors") || name.hasSuffix(".onnx") { return true }
        }
        return false
    }

    func selectModel(_ choice: String) {
        let previous = model
        model = choice
        guard choice != previous else { return }
        guard let root else {
            status = "找不到 CapsWriter 目录"
            return
        }
        let path = root + "/config_server.py"
        let text = (try? String(contentsOfFile: path, encoding: .utf8)) ?? ""
        do {
            let updated = try writeModelChoice(text, choice: choice)
            if updated != text {
                let url = URL(fileURLWithPath: path)
                let temporary = url.appendingPathExtension("partial")
                try updated.write(to: temporary, atomically: true, encoding: .utf8)
                _ = try FileManager.default.replaceItemAt(url, withItemAt: temporary)
                note("model saved")
                onConfigurationChanged()
            }
        } catch {
            model = previous
            status = "模型没有写入"
            note("model save failed")
        }
    }

    func beginPrepare() {
        guard !preparing, !ready else { return }
        guard root != nil else {
            status = "找不到 CapsWriter 目录"
            note("prepare failed")
            return
        }
        let stamped = readStampedModel()
        let launching = model
        loadedServerModel = loadedModelAfterProbe(stamped: stamped, launching: launching, portOpen: false)
        preparing = true
        ready = false
        lamp = .yellow
        readyText = "正在准备"
        prepareOutput = ""
        let port = serverPort()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let open = tcpPortOpen(host: "127.0.0.1", port: port)
            Task { @MainActor in
                guard let self else { return }
                self.loadedServerModel = loadedModelAfterProbe(
                    stamped: stamped, launching: launching, portOpen: open
                )
                if shouldRecordLaunchModel(stamped: stamped, portOpen: open) {
                    self.writeStampedModel(self.loadedServerModel)
                }
                self.launchPrepare()
            }
        }
    }

    private func launchPrepare() {
        guard let root else {
            preparing = false
            lamp = .red
            readyText = "还没准备好"
            status = "找不到 CapsWriter 目录"
            note("prepare failed")
            return
        }
        let start = startServer
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        configure(process, prepareLaunch(bundled: bundled, python: python, root: root, startServer: start))
        process.environment = unbuffered(ProcessInfo.processInfo.environment)
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            let text = String(data: data, encoding: .utf8) ?? ""
            Task { @MainActor in
                self?.prepareOutput += text
                self?.append(text)
            }
        }
        process.terminationHandler = { [weak self] process in
            Task { @MainActor in
                self?.finishPrepare(process)
            }
        }
        prepareProcess = process
        do {
            try process.run()
        } catch {
            preparing = false
            lamp = .red
            readyText = "还没准备好"
            status = "没能启动 Python"
            note("prepare failed")
        }
    }

    func start() {
        if busy { return }
        if !ready {
            status = "还没准备好"
            return
        }
        guard root != nil else {
            status = "找不到 CapsWriter 目录"
            return
        }
        do {
            _ = try batchArguments(
                target: target,
                recursive: recursive,
                splitLong: splitLong,
                force: force,
                hidden: hidden,
                startServer: startServer,
                stopServer: stopServer,
                model: model
            )
        } catch ShellError.emptyTarget {
            status = "先填入或打开一个文件、文件夹"
            return
        } catch {
            status = "不支持的模型"
            return
        }
        if serverMustRestart(loaded: loadedServerModel, selected: model) {
            beginModelSwitch()
            return
        }
        launchBatch()
    }

    private func launchBatch() {
        guard let root else {
            busy = false
            waitingForModelSwitch = false
            status = "找不到 CapsWriter 目录"
            return
        }
        let args: [String]
        do {
            args = try batchArguments(
                target: target,
                recursive: recursive,
                splitLong: splitLong,
                force: force,
                hidden: hidden,
                startServer: startServer,
                stopServer: stopServer,
                model: model
            )
        } catch ShellError.emptyTarget {
            busy = false
            status = "先填入或打开一个文件、文件夹"
            return
        } catch {
            busy = false
            status = "不支持的模型"
            return
        }
        stoppedByUser = false
        terminalLog = TerminalLog()
        batchCount = BatchCount()
        progressText = batchCount.text
        progressValue = 0
        progressTotal = 0
        busy = true
        status = "转录中"
        note("batch started")
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        configure(process, batchLaunch(bundled: bundled, python: python, root: root, arguments: args))
        process.environment = unbuffered(ProcessInfo.processInfo.environment)
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            let text = String(data: data, encoding: .utf8) ?? ""
            Task { @MainActor in self?.append(text) }
        }
        process.terminationHandler = { [weak self] process in
            Task { @MainActor in self?.finishBatch(process) }
        }
        batchProcess = process
        do {
            try process.run()
        } catch {
            busy = false
            status = "没有开始"
            note("batch finished 没有开始")
        }
    }

    func stop() {
        if status == "正在停止" {
            stopGeneration += 1
            forceStop()
            return
        }
        stoppedByUser = true
        let switching = waitingForModelSwitch
        waitingForModelSwitch = false
        if busy {
            status = switching ? "已停止" : "正在停止"
        }
        if switching {
            busy = false
            note("model switch cancelled")
        } else if busy {
            append("正在停止\n")
        }
        stopGeneration += 1
        let generation = stopGeneration
        signalRunning(SIGINT)
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 0.5) { [weak self] in
            Task { @MainActor in
                guard let self, self.stopGeneration == generation else { return }
                self.forceStop()
            }
        }
    }

    func attachLog(_ sink: @escaping ([LogEdit]) -> Void) {
        logSink = sink
        sink([.reset(logText)])
    }

    private func forceStop() {
        signalRunning(SIGKILL)
    }

    private func signalRunning(_ sig: Int32) {
        for process in [batchProcess, prepareProcess] {
            guard let process, process.isRunning else { continue }
            let pid = process.processIdentifier
            let targets = getpgid(pid) == pid
                ? stopPids(groupLeader: true, pid: pid)
                : transcriptionStopPids(root: pid, rows: Self.processRows())
            for target in targets {
                _ = kill(target, sig)
            }
        }
    }

    private static func processRows() -> [ProcessRow] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/ps")
        process.arguments = ["-axo", "pid=,ppid=,command="]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return []
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return parseProcessRows(String(data: data, encoding: .utf8) ?? "")
    }

    func stopBackground(done: @escaping () -> Void) {
        guard let root else {
            done()
            return
        }
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        configure(process, stopLaunch(bundled: bundled, python: python, root: root))
        process.environment = unbuffered(ProcessInfo.processInfo.environment)
        process.terminationHandler = { _ in
            Task { @MainActor in done() }
        }
        do {
            try process.run()
        } catch {
            done()
        }
    }

    func clientSettings() -> ClientSettings {
        guard let root,
              let text = try? String(contentsOfFile: root + "/config_client.py", encoding: .utf8) else {
            return ClientSettings()
        }
        return ClientSettings(text: text)
    }

    private func beginModelSwitch() {
        busy = true
        waitingForModelSwitch = true
        stoppedByUser = false
        status = "正在换成所选模型"
        note("model switch")
        let from = availableModels.first { $0.id == loadedServerModel }?.label ?? loadedServerModel
        let to = availableModels.first { $0.id == model }?.label ?? model
        append("服务端仍是 \(from)，正在换成 \(to)。\n")
        stopBackground { [weak self] in
            self?.probePort(attempt: 0)
        }
    }

    private func probePort(attempt: Int) {
        let port = serverPort()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let open = tcpPortOpen(host: "127.0.0.1", port: port)
            Task { @MainActor in
                self?.continueAfterProbe(open: open, attempt: attempt)
            }
        }
    }

    private func continueAfterProbe(open: Bool, attempt: Int) {
        guard waitingForModelSwitch else { return }
        switch portWait(open: open, attempt: attempt, limit: portWaitLimit) {
        case .closed:
            waitingForModelSwitch = false
            loadedServerModel = model
            writeStampedModel(model)
            launchBatch()
        case .stillOpen:
            waitingForModelSwitch = false
            busy = false
            status = "服务端还在用原来的模型"
            note("model switch failed")
            append("服务端还在用原来的模型\n")
        case .keepWaiting:
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 0.5) { [weak self] in
                Task { @MainActor in
                    self?.probePort(attempt: attempt + 1)
                }
            }
        }
    }

    private func serverPort() -> UInt16 {
        let port = clientSettings().port
        if port > 0 && port < 65536 { return UInt16(port) }
        return 6016
    }

    private func loadedModelFile() -> String? {
        guard let root else { return nil }
        return root + "/logs/loaded_model.txt"
    }

    private func readStampedModel() -> String? {
        guard let path = loadedModelFile() else { return nil }
        return try? String(contentsOfFile: path, encoding: .utf8)
    }

    private func writeStampedModel(_ choice: String) {
        guard let path = loadedModelFile() else { return }
        let url = URL(fileURLWithPath: path)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? (choice + "\n").write(to: url, atomically: true, encoding: .utf8)
    }

    private func finishPrepare(_ process: Process) {
        preparing = false
        prepareProcess = nil
        flushPartial()
        if process.terminationReason == .uncaughtSignal {
            ready = false
            lamp = .red
            readyText = "还没准备好"
            status = "已取消"
            note("prepare cancelled")
            return
        }
        if prepareSucceeded(prepareOutput) {
            ready = true
            lamp = .green
            readyText = "Ready"
            status = "空闲"
            note("prepare ready")
        } else {
            ready = false
            lamp = .red
            readyText = "还没准备好"
            let line = prepareOutput
                .split(whereSeparator: \.isNewline)
                .map { String($0).trimmingCharacters(in: .whitespaces) }
                .first { !$0.isEmpty } ?? "还没准备好"
            status = String(line.prefix(160))
            note("prepare failed")
        }
    }

    private func finishBatch(_ process: Process) {
        flushPartial()
        busy = false
        batchProcess = nil
        let label: String
        if stoppedByUser || process.terminationReason == .uncaughtSignal {
            label = "已停止"
        } else {
            label = batchExitLabel(Int(process.terminationStatus))
        }
        status = label
        note("batch finished \(label)")
    }

    private func append(_ text: String) {
        partial += text
        var edits: [LogEdit] = []
        while let range = partial.range(of: "\n") ?? partial.range(of: "\r") {
            let line = String(partial[..<range.lowerBound])
            partial.removeSubrange(..<range.upperBound)
            edits.append(contentsOf: stage(line))
        }
        deliver(coalesced(edits))
    }

    private func flushPartial() {
        if partial.isEmpty { return }
        let edits = stage(partial)
        partial = ""
        deliver(edits)
    }

    private func stage(_ line: String) -> [LogEdit] {
        let plain = plainLogLine(line)
        if plain.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return [] }
        let stamped = stampLine(plain, now: Date())
        guard logLineVisible(stamped, level: logLevel) else { return [] }
        if updateBatchCount(stamped, count: &batchCount) {
            progressText = batchCount.text
            progressValue = batchCount.fraction
            progressTotal = batchCount.total
        }
        guard let edit = terminalLog.ingest(stamped) else { return [] }
        switch edit {
        case .append(let row):
            if !logText.isEmpty && !logText.hasSuffix("\n") { logText += "\n" }
            logText += row + "\n"
        case .replace(let kind, let row):
            logText = replacingLastProgress(logText, kind: kind, with: row)
        case .reset(let text):
            logText = text
        }
        if logText.count > 200_000 {
            logText.removeFirst(logText.count - 200_000)
            if let newline = logText.firstIndex(of: "\n") {
                logText = String(logText[logText.index(after: newline)...])
            }
            return [.reset(logText)]
        }
        return [edit]
    }

    private func coalesced(_ edits: [LogEdit]) -> [LogEdit] {
        guard let index = edits.lastIndex(where: { if case .reset = $0 { return true }; return false }) else {
            return edits
        }
        return Array(edits[index...])
    }

    private func deliver(_ edits: [LogEdit]) {
        if edits.isEmpty { return }
        logSink?(edits)
    }

    private func configure(_ process: Process, _ launch: ProcessLaunch) {
        if launch.executable == "python3" {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3"] + launch.arguments
            return
        }
        process.executableURL = URL(fileURLWithPath: launch.executable)
        process.arguments = launch.arguments
    }

    private static func isRuntime(_ path: String) -> Bool {
        let base = URL(fileURLWithPath: path)
        let binary = base.appendingPathComponent("batch_transcribe").path
        let server = base.appendingPathComponent("start_server").path
        let config = base.appendingPathComponent("config_server.py").path
        return FileManager.default.isExecutableFile(atPath: binary)
            && FileManager.default.isExecutableFile(atPath: server)
            && FileManager.default.fileExists(atPath: config)
    }

    private func unbuffered(_ environment: [String: String]) -> [String: String] {
        pythonEnvironment(environment) { path in
            var isDirectory: ObjCBool = false
            return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
                && isDirectory.boolValue
        }
    }
}

private func tcpPortOpen(host: String, port: UInt16) -> Bool {
    let sock = socket(AF_INET, SOCK_STREAM, 0)
    if sock < 0 { return false }
    defer { close(sock) }
    var timeout = timeval(tv_sec: 0, tv_usec: 400_000)
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    var addr = sockaddr_in()
    addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = port.bigEndian
    if inet_pton(AF_INET, host, &addr.sin_addr) != 1 { return false }
    let result = withUnsafePointer(to: &addr) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return result == 0
}
