import Foundation
import CapsWriterCore

struct SettingField: Identifiable {
    var id: String
    var label: String
    var kind: String
    var help: String
    var recommended: Bool
    var boolValue: Bool
    var text: String
    var lines: [String]
    var pairs: [[String]]
}

struct SettingSection: Identifiable {
    var id: String { title }
    var title: String
    var fields: [SettingField]
}

struct SettingPage {
    var summary: [String]
    var sections: [SettingSection]
}

final class ConfigStore: ObservableObject {
    @Published var client = SettingPage(summary: [], sections: [])
    @Published var server = SettingPage(summary: [], sections: [])
    @Published var loaded = false
    @Published var loadError: String?
    @Published var status = ""
    @Published var saving = false
    @Published var unlocked: Set<String> = []
    @Published var clientLog = "还没有日志"
    @Published var serverLog = "还没有日志"

    let root: String?
    let python: String
    var note: (String) -> Void = { _ in }
    private var timer: Timer?

    init(root: String?, python: String) {
        self.root = root
        self.python = python
    }

    func reload() {
        loaded = false
        loadError = nil
        load()
    }

    func load() {
        reloadLogs()
        if timer == nil {
            timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
                self?.reloadLogs()
            }
        }
        guard root != nil else {
            loaded = true
            loadError = "找不到 CapsWriter 目录"
            return
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let result = self.run(arguments: ["-m", "core.tools.config_form", "dump"], input: nil)
            DispatchQueue.main.async {
                self.finishLoad(result)
            }
        }
    }

    func page(_ name: String) -> SettingPage {
        name == "server" ? server : client
    }

    func unlock(_ id: String) {
        unlocked.insert(id)
    }

    func save(updates: [[String: Any]], page name: String) {
        if updates.isEmpty {
            status = "没有改动"
            return
        }
        saving = true
        status = "正在写入"
        let data: Data
        do {
            data = try JSONSerialization.data(withJSONObject: ["updates": updates])
        } catch {
            saving = false
            status = "没能整理要写入的内容"
            return
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let result = self.run(arguments: ["-m", "core.tools.config_form", "apply"], input: data)
            DispatchQueue.main.async {
                self.saving = false
                if result.code == 0 {
                    self.applyBaseline(updates, page: name)
                    let file = name == "server" ? "config_server.py" : "config_client.py"
                    self.status = "已写入 \(file)。下次启动才生效。"
                    self.note("settings saved \(updates.count)")
                } else {
                    let message = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.status = message.isEmpty ? "没有写入" : message
                }
            }
        }
    }

    func reloadLogs() {
        guard let root else { return }
        let nextClient = tail(root + "/logs/client_latest.log")
        let nextServer = tail(root + "/logs/server_latest.log")
        if nextClient != clientLog { clientLog = nextClient }
        if nextServer != serverLog { serverLog = nextServer }
    }

    private func finishLoad(_ result: RunResult) {
        loaded = true
        guard result.code == 0,
              let data = result.stdout.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            loadError = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            if loadError?.isEmpty != false {
                loadError = "没有读到配置"
            }
            return
        }
        loadError = nil
        client = parsePage(json["client"])
        server = parsePage(json["server"])
        if client.sections.isEmpty || server.sections.isEmpty {
            loadError = "配置读出来是空的"
        }
    }

    private func applyBaseline(_ updates: [[String: Any]], page name: String) {
        if name == "server" {
            server = updated(server, updates)
        } else {
            client = updated(client, updates)
        }
    }

    private func updated(_ page: SettingPage, _ updates: [[String: Any]]) -> SettingPage {
        var copy = page
        for sectionIndex in copy.sections.indices {
            for fieldIndex in copy.sections[sectionIndex].fields.indices {
                let id = copy.sections[sectionIndex].fields[fieldIndex].id
                guard let update = updates.first(where: { $0["id"] as? String == id }) else { continue }
                var field = copy.sections[sectionIndex].fields[fieldIndex]
                let value = update["value"]
                switch field.kind {
                case "bool":
                    if let flag = value as? Bool {
                        field.boolValue = flag
                    }
                case "lines":
                    if let rows = value as? [String] {
                        field.lines = rows
                    }
                case "pairs":
                    if let rows = value as? [[String]] {
                        field.pairs = rows
                    }
                default:
                    if let text = value as? String {
                        field.text = text
                    }
                }
                copy.sections[sectionIndex].fields[fieldIndex] = field
            }
        }
        return copy
    }

    private func parsePage(_ value: Any?) -> SettingPage {
        guard let page = value as? [String: Any] else {
            return SettingPage(summary: [], sections: [])
        }
        let summary = page["summary"] as? [String] ?? []
        let rawSections = page["sections"] as? [[String: Any]] ?? []
        let sections = rawSections.map { raw -> SettingSection in
            let title = raw["title"] as? String ?? ""
            let rawFields = raw["fields"] as? [[String: Any]] ?? []
            return SettingSection(title: title, fields: rawFields.compactMap(parseField))
        }
        return SettingPage(summary: summary, sections: sections)
    }

    private func parseField(_ raw: [String: Any]) -> SettingField? {
        guard let id = raw["id"] as? String, let kind = raw["kind"] as? String else { return nil }
        let pairs = (raw["pairs"] as? [Any] ?? []).compactMap { item -> [String]? in
            guard let row = item as? [String], row.count == 2 else { return nil }
            return row
        }
        return SettingField(
            id: id,
            label: raw["label"] as? String ?? id,
            kind: kind,
            help: raw["help"] as? String ?? "",
            recommended: jsonBool(raw["recommended"]) ?? false,
            boolValue: jsonBool(raw["value"]) ?? false,
            text: raw["text"] as? String ?? "",
            lines: raw["lines"] as? [String] ?? [],
            pairs: pairs
        )
    }

    private func jsonBool(_ value: Any?) -> Bool? {
        guard let number = value as? NSNumber else { return nil }
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            return number.boolValue
        }
        return nil
    }

    private func tail(_ path: String) -> String {
        guard let handle = FileHandle(forReadingAtPath: path) else { return "还没有日志" }
        defer { try? handle.close() }
        let size = handle.seekToEndOfFile()
        if size > 65_536 {
            handle.seek(toFileOffset: size - 65_536)
        } else {
            handle.seek(toFileOffset: 0)
        }
        let data = handle.readDataToEndOfFile()
        guard let text = String(data: data, encoding: .utf8) else { return "还没有日志" }
        let rows = text.split(whereSeparator: \.isNewline).suffix(40)
        if rows.isEmpty { return "还没有日志" }
        return rows.joined(separator: "\n")
    }

    private struct RunResult {
        var code: Int32
        var stdout: String
        var stderr: String
    }

    private func run(arguments: [String], input: Data?) -> RunResult {
        guard let root else {
            return RunResult(code: 1, stdout: "", stderr: "找不到 CapsWriter 目录")
        }
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        if python == "python3" {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3"] + arguments
        } else {
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = arguments
        }
        process.environment = pythonEnvironment(ProcessInfo.processInfo.environment) { path in
            var isDirectory: ObjCBool = false
            return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) && isDirectory.boolValue
        }
        let output = Pipe()
        let error = Pipe()
        process.standardOutput = output
        process.standardError = error
        let inputPipe = Pipe()
        if input != nil {
            process.standardInput = inputPipe
        }
        do {
            try process.run()
        } catch {
            return RunResult(code: 1, stdout: "", stderr: "没能启动 Python")
        }
        if let input {
            inputPipe.fileHandleForWriting.write(input)
            try? inputPipe.fileHandleForWriting.close()
        }
        let outData = output.fileHandleForReading.readDataToEndOfFile()
        let errData = error.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return RunResult(
            code: process.terminationStatus,
            stdout: String(data: outData, encoding: .utf8) ?? "",
            stderr: String(data: errData, encoding: .utf8) ?? ""
        )
    }
}
