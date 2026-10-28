import Combine
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
    @Published var logLevel = "INFO"
    @Published var lamp: Lamp = .red
    @Published var readyText = "还没准备好"
    @Published var status = "空闲"
    @Published var log = ""
    @Published var ready = false
    @Published var busy = false
    @Published var preparing = false

    let root: String?
    let python: String
    let bundled: Bool
    var note: (String) -> Void = { _ in }

    private var partial = ""
    private var progressLog = ProgressLog()
    private var prepareProcess: Process?
    private var batchProcess: Process?
    private var stoppedByUser = false
    private var prepareOutput = ""

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
            model = readModelType(config)
        }
    }

    func beginPrepare() {
        guard !preparing, !ready else { return }
        guard let root else {
            status = "找不到 CapsWriter 目录"
            note("prepare failed")
            return
        }
        preparing = true
        ready = false
        lamp = .yellow
        readyText = "正在准备"
        prepareOutput = ""
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
        guard let root else {
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
            status = "先填入或打开一个文件、文件夹"
            return
        } catch {
            status = "不支持的模型"
            return
        }
        stoppedByUser = false
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
        stoppedByUser = true
        if busy {
            status = "正在停止"
        }
        if let batchProcess, batchProcess.isRunning {
            batchProcess.terminate()
        }
        if let prepareProcess, prepareProcess.isRunning {
            prepareProcess.terminate()
        }
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
        while let range = partial.range(of: "\n") ?? partial.range(of: "\r") {
            let line = String(partial[..<range.lowerBound])
            partial.removeSubrange(..<range.upperBound)
            publish(line)
        }
    }

    private func flushPartial() {
        if partial.isEmpty { return }
        publish(partial)
        partial = ""
    }

    private func publish(_ line: String) {
        let now = Date()
        let stamped = stampLine(line, now: now)
        guard logLineVisible(stamped, level: logLevel) else { return }
        guard progressLog.keep(stamped, at: now) else { return }
        log += stamped + "\n"
        if log.count > 200_000 {
            log.removeFirst(log.count - 200_000)
        }
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
