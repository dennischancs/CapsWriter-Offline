import Foundation

public let modelCatalog: [(id: String, label: String, folders: [String])] = [
    ("sensevoice", "SenseVoice Small", ["SenseVoiceSmall"]),
    ("fun_asr_nano", "Fun-ASR Nano", ["Fun-ASR-Nano-2512"]),
    ("qwen_asr:1.7b", "Qwen3-ASR 1.7B 8bit", ["Qwen3-ASR-1.7B-8bit"]),
    ("qwen_asr:1.7b-6bit", "Qwen3-ASR 1.7B 6bit", ["Qwen3-ASR-1.7B-6bit"]),
    ("qwen_asr:1.7b-4bit", "Qwen3-ASR 1.7B 4bit", ["Qwen3-ASR-1.7B-4bit"]),
    ("qwen_asr:1.7b-mxfp4", "Qwen3-ASR 1.7B mxfp4", ["Qwen3-ASR-1.7B-mxfp4"]),
    ("qwen_asr:0.6b", "Qwen3-ASR 0.6B 8bit", ["Qwen3-ASR-0.6B-8bit"]),
    ("qwen_asr:0.6b-6bit", "Qwen3-ASR 0.6B 6bit", ["Qwen3-ASR-0.6B-6bit"]),
    ("qwen_asr:0.6b-4bit", "Qwen3-ASR 0.6B 4bit", ["Qwen3-ASR-0.6B-4bit"]),
    ("qwen_asr:0.6b-mxfp4", "Qwen3-ASR 0.6B mxfp4", ["Qwen3-ASR-0.6B-mxfp4"]),
    ("paraformer", "Paraformer", ["Paraformer"]),
]

public let modelChoices = modelCatalog.map { (id: $0.id, label: $0.label) }

public let modelIDs = ["sensevoice", "fun_asr_nano", "qwen_asr", "paraformer"]
public let qwenVariants = [
    "1.7b", "1.7b-8bit", "1.7b-6bit", "1.7b-4bit", "1.7b-mxfp4",
    "0.6b", "0.6b-8bit", "0.6b-6bit", "0.6b-4bit", "0.6b-mxfp4",
]
public let qwenLargeMemory: UInt64 = 16 * 1024 * 1024 * 1024
public let logLevels = ["DEBUG", "INFO", "WARNING", "ERROR"]
public let homebrewPython = "/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3"
public let launchToolDirectories = ["/opt/homebrew/bin", "/usr/local/bin"]

public enum ShellError: Error, Equatable {
    case emptyTarget
    case unsupportedModel(String)
    case missingModelLine
}

public enum CloseChoice: String, Equatable {
    case tray
    case quit
}

public struct ClientSettings: Equatable {
    public var addr = "127.0.0.1"
    public var port = 6016
    public var threshold = 0.3
    public var segmentDuration = 60.0
    public var segmentOverlap = 4.0
    public var context = ""
    public var language = "auto"
    public var trashPunctuation = "，。,."
    public var trashThreshold = 8

    public init() {}

    public init(text: String) {
        self.init()
        if let value = stringSetting("addr", text) { addr = value }
        if let value = numberSetting("port", text) { port = Int(value) }
        if let value = numberSetting("threshold", text) { threshold = value }
        if let value = numberSetting("mic_seg_duration", text) { segmentDuration = value }
        if let value = numberSetting("mic_seg_overlap", text) { segmentOverlap = value }
        if let value = stringSetting("context", text) { context = value }
        if let value = stringSetting("language", text) { language = value }
        if let value = stringSetting("trash_punc", text) { trashPunctuation = value }
        if let value = numberSetting("trash_punc_thresh", text) { trashThreshold = Int(value) }
    }
}

public struct ShellLog {
    public private(set) var lines: [String] = []
    public let capacity: Int

    public init(capacity: Int = 200) {
        self.capacity = capacity
    }

    /// kind 只记事件名。换行折进同一行，避免把识别正文写进来。
    public mutating func record(_ kind: String, at date: Date, persist: (String) -> Bool) {
        let clean = kind
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
        let line = "\(iso8601(date)) \(clean)"
        lines.append(line)
        if lines.count > capacity {
            lines.removeFirst(lines.count - capacity)
        }
        _ = persist(line)
    }
}

public func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.string(from: date)
}

public func batchArguments(
    target: String,
    recursive: Bool,
    splitLong: Bool,
    force: Bool,
    hidden: Bool,
    startServer: Bool,
    stopServer: Bool,
    model: String
) throws -> [String] {
    let trimmed = target.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
        throw ShellError.emptyTarget
    }
    guard acceptsModelArgument(model) else {
        throw ShellError.unsupportedModel(model)
    }
    var args = [trimmed, "--model", model]
    if !recursive { args.append("--no-recursive") }
    if !splitLong { args.append("--no-long-fallback") }
    if force { args.append("--force") }
    if hidden { args.append("--hidden") }
    if !startServer { args.append("--no-start-server") }
    if stopServer { args.append("--stop-server") }
    return args
}

/// Finder 启动的 app 只有 /usr/bin:/bin:/usr/sbin:/sbin。把存在的工具目录加在前面，原来的 PATH 原样留着。
public func pythonEnvironment(
    _ environment: [String: String],
    directoryExists: (String) -> Bool
) -> [String: String] {
    var copy = environment
    copy["PYTHONUNBUFFERED"] = "1"
    let existing = copy["PATH"] ?? ""
    let present = Set(existing.split(separator: ":", omittingEmptySubsequences: true).map(String.init))
    let prefix = launchToolDirectories.filter { directoryExists($0) && !present.contains($0) }
    guard !prefix.isEmpty else { return copy }
    let joined = prefix.joined(separator: ":")
    copy["PATH"] = existing.isEmpty ? joined : joined + ":" + existing
    return copy
}

public let progressInterval: TimeInterval = 60

public func progressKind(_ line: String) -> String? {
    if line.contains("发送进度") { return "send" }
    if line.contains("转录进度") { return "transcribe" }
    return nil
}

public func progressNumerator(_ line: String) -> Double? {
    for marker in ["发送进度：", "转录进度："] {
        guard let range = line.range(of: marker) else { continue }
        var digits = ""
        var sawDot = false
        for character in line[range.upperBound...] {
            if character.isNumber {
                digits.append(character)
            } else if character == "." && !sawDot && !digits.isEmpty {
                sawDot = true
                digits.append(character)
            } else if digits.isEmpty && character == " " {
                continue
            } else {
                break
            }
        }
        return Double(digits)
    }
    return nil
}

public enum ProgressEdit: Equatable {
    case drop
    case append
    case replace(String)
}

public struct ProgressLog {
    public let interval: TimeInterval
    private var last: [String: Double] = [:]

    public init(interval: TimeInterval = progressInterval) {
        self.interval = interval
    }

    /// 同一种进度原地改。分子变小是下一个文件，才另起一行。完成、失败和文件名始终另起一行。
    public mutating func edit(_ line: String) -> ProgressEdit {
        guard let kind = progressKind(line), let value = progressNumerator(line) else { return .append }
        if let previous = last[kind] {
            if abs(previous - value) < 0.001 { return .drop }
            if value + 0.001 < previous {
                last[kind] = value
                return .append
            }
            last[kind] = value
            return .replace(kind)
        }
        last[kind] = value
        return .append
    }

    public mutating func apply(_ log: inout String, _ line: String) {
        switch edit(line) {
        case .drop:
            return
        case .append:
            if !log.isEmpty && !log.hasSuffix("\n") { log += "\n" }
            log += line + "\n"
        case .replace(let kind):
            log = replacingLastProgress(log, kind: kind, with: line)
        }
    }
}

public func replacingLastProgress(_ log: String, kind: String, with line: String) -> String {
    let marker = kind == "send" ? "发送进度" : "转录进度"
    let body = log.hasSuffix("\n") ? String(log.dropLast()) : log
    var lines = body.isEmpty
        ? [String]()
        : body.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    if let index = lines.lastIndex(where: { $0.contains(marker) }) {
        lines[index] = line
    } else {
        lines.append(line)
    }
    return lines.joined(separator: "\n") + "\n"
}

public struct ProcessLaunch: Equatable {
    public var executable: String
    public var arguments: [String]

    public init(executable: String, arguments: [String]) {
        self.executable = executable
        self.arguments = arguments
    }
}

public func bundledRuntimePath(_ bundlePath: String) -> String {
    var path = bundlePath
    if path.hasSuffix("/") { path.removeLast() }
    return path + "/Contents/Resources/runtime"
}

public func preferBundledRuntime(bundlePath: String, isRuntime: (String) -> Bool) -> String? {
    let runtime = bundledRuntimePath(bundlePath)
    return isRuntime(runtime) ? runtime : nil
}

public func prepareLaunch(bundled: Bool, python: String, root: String, startServer: Bool) -> ProcessLaunch {
    if bundled {
        var args = ["--prepare"]
        if !startServer { args.append("--no-start-server") }
        return ProcessLaunch(executable: root + "/batch_transcribe", arguments: args)
    }
    let flag = startServer ? "True" : "False"
    let code = "import batch_transcribe as b; print(b.prepare_server(start=\(flag), timeout=180))"
    return ProcessLaunch(executable: python, arguments: ["-c", code])
}

public func batchLaunch(bundled: Bool, python: String, root: String, arguments: [String]) -> ProcessLaunch {
    if bundled {
        return ProcessLaunch(executable: root + "/batch_transcribe", arguments: arguments)
    }
    return ProcessLaunch(executable: python, arguments: [root + "/batch_transcribe.py"] + arguments)
}

public func stopLaunch(bundled: Bool, python: String, root: String) -> ProcessLaunch {
    if bundled {
        return ProcessLaunch(executable: root + "/batch_transcribe", arguments: ["--stop-background"])
    }
    let code = "import batch_transcribe as b; b.stop_background_servers(b.ROOT, b.server_endpoint()[1])"
    return ProcessLaunch(executable: python, arguments: ["-c", code])
}

public func batchExitLabel(_ code: Int) -> String {
    if code == 130 { return "已停止" }
    if code == 0 { return "完成" }
    if code == 1 { return "完成，有失败" }
    return "没有开始"
}

public func readCloseChoice(_ text: String?) -> CloseChoice? {
    guard let text else { return nil }
    return CloseChoice(rawValue: text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
}

public struct ClosePrompt: Equatable {
    public var choice: CloseChoice
    public var remember: Bool

    public init(choice: CloseChoice, remember: Bool) {
        self.choice = choice
        self.remember = remember
    }
}

public enum CloseResolution: Equatable {
    case tray(persist: Bool)
    case quit(persist: Bool)
    case stay
}

/// 已经记住的选择直接用。没记住时，只有勾选了才写入。关掉问句不算选择。
public func resolveClose(saved: CloseChoice?, prompt: ClosePrompt?) -> CloseResolution {
    if let saved {
        switch saved {
        case .tray: return .tray(persist: false)
        case .quit: return .quit(persist: false)
        }
    }
    guard let prompt else { return .stay }
    switch prompt.choice {
    case .tray: return .tray(persist: prompt.remember)
    case .quit: return .quit(persist: prompt.remember)
    }
}

/// 左键打开窗口。右键或按住 Control 再点，打开菜单。
public func statusClickOpensMenu(rightButton: Bool, control: Bool) -> Bool {
    rightButton || control
}

public func firstDroppedPath(_ paths: [String]) -> String? {
    for path in paths {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { return trimmed }
    }
    return nil
}

public func prepareSucceeded(_ output: String) -> Bool {
    let lines = output
        .split(whereSeparator: \.isNewline)
        .map { $0.trimmingCharacters(in: .whitespaces) }
        .filter { !$0.isEmpty }
    guard let last = lines.last else { return false }
    return last.hasPrefix("ready ")
}

public func findRepositoryRoot(starts: [String], isRoot: (String) -> Bool) -> String? {
    var seen = Set<String>()
    for start in starts where !start.isEmpty {
        var url = URL(fileURLWithPath: start).standardizedFileURL
        var previous = ""
        while previous != url.path && !seen.contains(url.path) {
            seen.insert(url.path)
            if isRoot(url.path) { return url.path }
            previous = url.path
            url.deleteLastPathComponent()
        }
    }
    return nil
}

public func resolvePython(environment: String?, isExecutable: (String) -> Bool) -> String {
    if let environment, isExecutable(environment) { return environment }
    if isExecutable(homebrewPython) { return homebrewPython }
    return "python3"
}

public func directoryHasWeights(_ path: String, isDirectory: (String) -> Bool, containsFile: (String, String) -> Bool) -> Bool {
    if !isDirectory(path) { return false }
    let names = ["model.safetensors", "model.onnx", "model.int8.onnx", "encoder.onnx"]
    if names.contains(where: { containsFile(path, $0) }) { return true }
    return containsFile(path, "*")
}

/// 只返回本地已经放好权重的项。Paraformer 看 models/Paraformer，其余看 models/mlx。
public func installedModelChoices(root: String, isDirectory: (String) -> Bool, containsFile: (String, String) -> Bool) -> [(id: String, label: String)] {
    modelCatalog.filter { item in
        if item.id == "paraformer" {
            return directoryHasWeights(root + "/models/Paraformer", isDirectory: isDirectory, containsFile: containsFile)
        }
        return item.folders.contains { folder in
            directoryHasWeights(root + "/models/mlx/" + folder, isDirectory: isDirectory, containsFile: containsFile)
        }
    }.map { (id: $0.id, label: $0.label) }
}

public func acceptsModelArgument(_ model: String) -> Bool {
    if modelChoices.contains(where: { $0.id == model }) { return true }
    return modelIDs.contains(model)
}

public func readModelType(_ text: String) -> String {
    guard let found = firstCapture("model_type\\s*=\\s*['\\\"]([A-Za-z0-9_]+)['\\\"]", in: text),
          modelIDs.contains(found) else {
        return modelIDs[0]
    }
    return found
}

public func readQwenVariant(_ text: String) -> String {
    guard let found = firstCapture(
        "(?m)^[ \t]*qwen_mlx_variant\\s*=\\s*['\"]([A-Za-z0-9_.-]+)['\"]",
        in: text
    ) else {
        return "auto"
    }
    let aliases = [
        "1.7": "1.7b", "1.7b": "1.7b",
        "1.7b-8bit": "1.7b-8bit", "1.7b-6bit": "1.7b-6bit",
        "1.7b-4bit": "1.7b-4bit", "1.7b-mxfp4": "1.7b-mxfp4",
        "0.6": "0.6b", "0.6b": "0.6b",
        "0.6b-8bit": "0.6b-8bit", "0.6b-6bit": "0.6b-6bit",
        "0.6b-4bit": "0.6b-4bit", "0.6b-mxfp4": "0.6b-mxfp4",
    ]
    return aliases[found.lowercased()] ?? "auto"
}

/// auto 不单列。统一内存达到 16GB 时显示 1.7B，否则显示 0.6B。
public func readModelChoice(_ text: String, memory: UInt64) -> String {
    let engine = readModelType(text)
    guard engine == "qwen_asr" else { return engine }
    let variant = readQwenVariant(text)
    let size: String
    if qwenVariants.contains(variant) {
        size = variant
    } else {
        size = memory >= qwenLargeMemory ? "1.7b" : "0.6b"
    }
    return "qwen_asr:\(size)"
}

public func writeModelType(_ text: String, model: String) throws -> String {
    guard modelIDs.contains(model) else {
        throw ShellError.unsupportedModel(model)
    }
    let pattern = "(model_type\\s*=\\s*['\\\"])[A-Za-z0-9_]+(['\\\"])"
    let regex = try NSRegularExpression(pattern: pattern)
    let range = NSRange(text.startIndex..., in: text)
    if regex.numberOfMatches(in: text, range: range) != 1 {
        throw ShellError.missingModelLine
    }
    return regex.stringByReplacingMatches(in: text, range: range, withTemplate: "$1\(model)$2")
}

public func writeQwenVariant(_ text: String, variant: String) throws -> String {
    guard qwenVariants.contains(variant) else {
        throw ShellError.unsupportedModel(variant)
    }
    let pattern = #"(?m)^([ \t]*qwen_mlx_variant\s*=\s*['"])[A-Za-z0-9_.-]+(['"])"#
    let regex = try NSRegularExpression(pattern: pattern)
    let range = NSRange(text.startIndex..., in: text)
    if regex.numberOfMatches(in: text, range: range) != 1 {
        throw ShellError.missingModelLine
    }
    return regex.stringByReplacingMatches(in: text, range: range, withTemplate: "$1\(variant)$2")
}

public func writeModelChoice(_ text: String, choice: String) throws -> String {
    let parts = choice.split(separator: ":", maxSplits: 1).map(String.init)
    let engine = parts.first ?? ""
    guard modelIDs.contains(engine) else {
        throw ShellError.unsupportedModel(choice)
    }
    var updated = try writeModelType(text, model: engine)
    if parts.count == 2 {
        let variant = parts[1]
        guard engine == "qwen_asr", qwenVariants.contains(variant) else {
            throw ShellError.unsupportedModel(choice)
        }
        updated = try writeQwenVariant(updated, variant: variant)
    }
    return updated
}

public func stampLine(_ line: String, now: Date) -> String {
    if line.range(of: #"^\[\d{4}-\d{2}-\d{2} \d\d:\d\d:\d\d\.\d{3}\]"#, options: .regularExpression) != nil {
        return line
    }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss."
    let milliseconds = Calendar(identifier: .gregorian).component(.nanosecond, from: now) / 1_000_000
    let prefix = "[\(formatter.string(from: now))\(String(format: "%03d", milliseconds))]"
    if line.isEmpty { return prefix }
    return "\(prefix) \(line)"
}

public func logLineVisible(_ line: String, level: String) -> Bool {
    let ranks = ["DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3]
    let rank = ranks[level.uppercased()] ?? ranks["INFO"]!
    let pattern = "^(?:\\[?\\d{4}-\\d{2}-\\d{2}[ T]\\d\\d:\\d\\d:\\d\\d(?:\\.\\d+)?\\]?\\s+)?([A-Z]{4,8})\\b"
    guard let token = firstCapture(pattern, in: line), let found = ranks[token] else {
        return true
    }
    return found >= rank
}

public func semanticUnitCount(_ text: String) -> Int {
    let pattern = "[\u{4e00}-\u{9fff}\u{3400}-\u{4dbf}\u{f900}-\u{faff}]|[A-Za-z]+|\\d+"
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return 0 }
    return regex.numberOfMatches(in: text, range: NSRange(text.startIndex..., in: text))
}

public func stripTrailingPunctuation(_ text: String, marks: String, threshold: Int) -> String {
    guard text.count > 1, !marks.isEmpty else { return text }
    if threshold > 0 && semanticUnitCount(text) > threshold { return text }
    guard let last = text.last, marks.contains(last) else { return text }
    return String(text.dropLast())
}

public let rightOptionKeyCode: UInt16 = 61
public let silencePeak: Float = 0.001

public enum DictationOutcome: String, Equatable {
    case short
    case silent
    case text
    case empty
}

public func classifyDictation(duration: Double, threshold: Double, peak: Float, text: String) -> DictationOutcome {
    if duration < threshold { return .short }
    if peak < silencePeak { return .silent }
    if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return .empty }
    return .text
}

public func dictationStatus(_ outcome: DictationOutcome) -> String {
    switch outcome {
    case .short: return "按得太短"
    case .silent: return "这段录音是静音"
    case .text: return "已粘贴"
    case .empty: return "识别结果为空"
    }
}

public func downsampleChannelMean(_ samples: [Float], channels: Int, factor: Int) -> [Float] {
    guard channels > 0, factor > 0, !samples.isEmpty else { return [] }
    let frames = samples.count / channels
    var output: [Float] = []
    var frame = 0
    while frame < frames {
        let base = frame * channels
        if base + channels > samples.count { break }
        var sum: Float = 0
        for channel in 0..<channels {
            sum += samples[base + channel]
        }
        output.append(sum / Float(channels))
        frame += factor
    }
    return output
}

public func toRecognitionRate(_ samples: [Float], channels: Int, sampleRate: Double) -> [Float] {
    guard channels > 0, sampleRate > 0 else { return [] }
    let ratio = sampleRate / 16000
    let factor = max(1, Int(ratio.rounded()))
    if abs(ratio - Double(factor)) < 0.01 {
        return downsampleChannelMean(samples, channels: channels, factor: factor)
    }
    return downsampleChannelMean(samples, channels: channels, factor: 1)
}

public func audioMessageJSON(
    taskID: String,
    samples: [Float],
    isFinal: Bool,
    timeStart: Double,
    segmentDuration: Double,
    segmentOverlap: Double,
    context: String,
    language: String
) -> String {
    var bytes = Data(capacity: samples.count * 4)
    for sample in samples {
        var value = sample.bitPattern.littleEndian
        withUnsafeBytes(of: &value) { bytes.append(contentsOf: $0) }
    }
    let payload: [String: Any] = [
        "task_id": taskID,
        "source": "mic",
        "data": bytes.base64EncodedString(),
        "is_final": isFinal,
        "time_start": timeStart,
        "seg_duration": segmentDuration,
        "seg_overlap": segmentOverlap,
        "context": context,
        "language": language,
    ]
    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
          let text = String(data: data, encoding: .utf8) else {
        return "{}"
    }
    return text
}

public enum PortWait: Equatable {
    case closed
    case keepWaiting
    case stillOpen
}

/// 已经记下的模型和这次选择不同，才停掉旧服务端。没记过，或没换，就不重启。
public func serverMustRestart(loaded: String, selected: String) -> Bool {
    !loaded.isEmpty && loaded != selected
}

/// 文件里是进程实际加载的模型。没有这份记录时，才用这次准备要拉起的菜单项。
public func rememberedServerModel(stamped: String?, launching: String) -> String {
    let saved = stamped?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !saved.isEmpty { return saved }
    return launching
}

/// 没有记录、端口上却已经有服务端时，不能把菜单上的模型当成进程里的模型。
public func loadedModelAfterProbe(stamped: String?, launching: String, portOpen: Bool) -> String {
    let missing = stamped?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false
    if missing && portOpen { return "unknown" }
    return rememberedServerModel(stamped: stamped, launching: launching)
}

/// 只有端口本来是空的，才把这次准备要拉起的模型记下来。
public func shouldRecordLaunchModel(stamped: String?, portOpen: Bool) -> Bool {
    let missing = stamped?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false
    return missing && !portOpen
}

/// attempt 从 0 数。端口关了就停。还开着并且没到次数，再等一次。到了仍开着就放弃。
public func portWait(open: Bool, attempt: Int, limit: Int) -> PortWait {
    if !open { return .closed }
    if attempt + 1 >= limit { return .stillOpen }
    return .keepWaiting
}

public func recognitionText(from json: String) -> (taskID: String, isFinal: Bool, text: String)? {
    guard let data = json.data(using: .utf8),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let taskID = object["task_id"] as? String,
          let text = object["text"] as? String else {
        return nil
    }
    return (taskID, object["is_final"] as? Bool ?? false, text)
}

private func stringSetting(_ name: String, _ text: String) -> String? {
    firstCapture("(?m)^\\s*\(name)\\s*=\\s*['\\\"]([^'\\\"]*)['\\\"]", in: text)
}

private func numberSetting(_ name: String, _ text: String) -> Double? {
    guard let raw = firstCapture("(?m)^\\s*\(name)\\s*=\\s*['\\\"]?([0-9]+(?:\\.[0-9]+)?)['\\\"]?", in: text) else {
        return nil
    }
    return Double(raw)
}

private func firstCapture(_ pattern: String, in text: String) -> String? {
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
    let range = NSRange(text.startIndex..., in: text)
    guard let match = regex.firstMatch(in: text, range: range),
          match.numberOfRanges > 1,
          let token = Range(match.range(at: 1), in: text) else {
        return nil
    }
    return String(text[token])
}


public struct BatchCount: Equatable {
    public var current: Int
    public var total: Int

    public init(current: Int = 0, total: Int = 0) {
        self.current = current
        self.total = total
    }

    public var text: String {
        "当前 \(current) / 总计 \(total)"
    }

    public var fraction: Double {
        guard total > 0 else { return 0 }
        return min(1, max(0, Double(current) / Double(total)))
    }
}

public func updateBatchCount(_ line: String, count: inout BatchCount) -> Bool {
    let text = plainLogLine(line)
    if let pending = firstInt(#"待转录\s+(\d+)\s*个"#, in: text) {
        count.total = pending
        count.current = 0
        return true
    }
    if let pair = firstPair(#"\[(\d+)\s*/\s*(\d+)\]"#, in: text) {
        count.current = pair.0
        count.total = pair.1
        return true
    }
    return false
}

public enum LogEdit: Equatable {
    case append(String)
    case replace(kind: String, line: String)
    case reset(String)
}

public struct TerminalLog {
    private var progress = ProgressLog()

    public init() {}

    public mutating func ingest(_ line: String) -> LogEdit? {
        switch progress.edit(line) {
        case .drop:
            return nil
        case .append:
            return .append(line)
        case .replace(let kind):
            return .replace(kind: kind, line: line)
        }
    }
}

public func logShouldFollow(distanceFromBottom: Double, threshold: Double = 36) -> Bool {
    distanceFromBottom <= threshold
}

public func plainLogLine(_ line: String) -> String {
    var text = line.replacingOccurrences(of: "\r", with: "")
    text = text.replacingOccurrences(of: "\u{0008}", with: "")
    let pattern = "\u{001B}\\[[0-9;?]*[ -/]*[@-~]"
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
    let range = NSRange(text.startIndex..., in: text)
    return regex.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: "")
}

public func stopPids(groupLeader: Bool, pid: Int32) -> [Int32] {
    if pid <= 0 { return [] }
    if groupLeader { return [-pid] }
    return [pid]
}

public struct ProcessRow: Equatable {
    public var pid: Int32
    public var parent: Int32
    public var command: String

    public init(pid: Int32, parent: Int32, command: String) {
        self.pid = pid
        self.parent = parent
        self.command = command
    }
}

public func parseProcessRows(_ text: String) -> [ProcessRow] {
    var rows: [ProcessRow] = []
    for line in text.split(whereSeparator: \.isNewline) {
        let parts = line.split(maxSplits: 2, omittingEmptySubsequences: true, whereSeparator: { $0 == " " || $0 == "\t" })
        guard parts.count >= 2,
              let pid = Int32(parts[0]),
              let parent = Int32(parts[1]) else { continue }
        let command = parts.count == 3 ? String(parts[2]) : ""
        rows.append(ProcessRow(pid: pid, parent: parent, command: command))
    }
    return rows
}

public func keepsServerProcess(_ command: String) -> Bool {
    if command.localizedCaseInsensitiveContains("CapsWriter Server") { return true }
    let tokens = command.split(maxSplits: 3, omittingEmptySubsequences: true, whereSeparator: { $0 == " " || $0 == "\t" })
    for token in tokens {
        let base = (token as NSString).lastPathComponent
        if base == "start_server" || base == "start_server.exe" || base == "start_server.py" {
            return true
        }
    }
    return false
}

/// 批量进程不是组长时，不能对整个组发信号，否则会打到外壳自己。
/// 只结束它下面的 ffmpeg 等子进程，已经加载的服务端留下。
public func transcriptionStopPids(root: Int32, rows: [ProcessRow]) -> [Int32] {
    if root <= 0 { return [] }
    var children: [Int32: [Int32]] = [:]
    var commands: [Int32: String] = [:]
    for row in rows {
        children[row.parent, default: []].append(row.pid)
        commands[row.pid] = row.command
    }
    var ordered: [Int32] = []
    var seen = Set<Int32>()
    func walk(_ pid: Int32) {
        for child in children[pid] ?? [] {
            if !seen.insert(child).inserted { continue }
            if keepsServerProcess(commands[child] ?? "") { continue }
            walk(child)
            ordered.append(child)
        }
    }
    walk(root)
    ordered.append(root)
    return ordered
}

private func firstInt(_ pattern: String, in text: String) -> Int? {
    guard let token = firstCapture(pattern, in: text) else { return nil }
    return Int(token)
}

private func firstPair(_ pattern: String, in text: String) -> (Int, Int)? {
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
    let range = NSRange(text.startIndex..., in: text)
    guard let match = regex.firstMatch(in: text, range: range),
          match.numberOfRanges > 2,
          let left = Range(match.range(at: 1), in: text),
          let right = Range(match.range(at: 2), in: text),
          let current = Int(text[left]),
          let total = Int(text[right]) else {
        return nil
    }
    return (current, total)
}
