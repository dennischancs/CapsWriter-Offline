import XCTest
@testable import CapsWriterCore

final class ShellCoreTests: XCTestCase {
    func testArgumentsMatchTheBatchForm() throws {
        let args = try batchArguments(
            target: "  /tmp/media  ",
            recursive: true,
            splitLong: true,
            force: false,
            hidden: false,
            startServer: true,
            stopServer: false,
            model: "sensevoice"
        )
        XCTAssertEqual(args, ["/tmp/media", "--model", "sensevoice"])
        XCTAssertFalse(args.contains("--server-timeout"))
        XCTAssertFalse(args.contains("--timeout-factor"))
        XCTAssertFalse(args.contains("--min-timeout"))
        XCTAssertFalse(args.contains("--segment-seconds"))
    }

    func testUncheckedOptionsBecomeTheScriptFlags() throws {
        let args = try batchArguments(
            target: "/tmp/talk.m4a",
            recursive: false,
            splitLong: false,
            force: true,
            hidden: true,
            startServer: false,
            stopServer: true,
            model: "qwen_asr"
        )
        XCTAssertEqual(args, [
            "/tmp/talk.m4a", "--model", "qwen_asr",
            "--no-recursive", "--no-long-fallback", "--force", "--hidden",
            "--no-start-server", "--stop-server",
        ])
    }

    func testEmptyTargetAndUnknownModelFail() {
        XCTAssertThrowsError(try batchArguments(
            target: "  ",
            recursive: true, splitLong: true, force: false, hidden: false,
            startServer: true, stopServer: false, model: "sensevoice"
        )) { error in
            XCTAssertEqual(error as? ShellError, .emptyTarget)
        }
        XCTAssertThrowsError(try batchArguments(
            target: "/tmp",
            recursive: true, splitLong: true, force: false, hidden: false,
            startServer: true, stopServer: false, model: "whisper"
        ))
    }

    func testLogLevelHidesDebugAndKeepsProgress() {
        XCTAssertFalse(logLineVisible("DEBUG 细节", level: "INFO"))
        XCTAssertTrue(logLineVisible("[2026-10-28 01:02:03.004] INFO 开始", level: "INFO"))
        XCTAssertTrue(logLineVisible("找到 2 个音视频", level: "ERROR"))
        XCTAssertTrue(logLineVisible("WARNING 慢", level: "INFO"))
        XCTAssertFalse(logLineVisible("INFO 普通", level: "ERROR"))
    }

    func testStampSkipsALineThatAlreadyHasATime() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let stamped = stampLine("进度", now: now)
        XCTAssertTrue(stamped.contains("] 进度"))
        XCTAssertEqual(stampLine(stamped, now: now), stamped)
        XCTAssertFalse(stampLine("", now: now).contains("  "))
    }

    func testModelLineIsReplacedOnce() throws {
        let source = "model_type = 'sensevoice'\nport = '6016'\n"
        XCTAssertEqual(readModelType(source), "sensevoice")
        XCTAssertEqual(readModelType("nope"), "sensevoice")
        let updated = try writeModelType(source, model: "qwen_asr")
        XCTAssertEqual(updated, "model_type = 'qwen_asr'\nport = '6016'\n")
        XCTAssertThrowsError(try writeModelType("port = 1\n", model: "qwen_asr"))
    }

    func testCloseChoiceAndFirstDrop() {
        XCTAssertEqual(readCloseChoice(" Tray \n"), .tray)
        XCTAssertNil(readCloseChoice("later"))
        XCTAssertNil(readCloseChoice(nil))
        XCTAssertEqual(resolveClose(saved: .tray, prompt: nil), .tray(persist: false))
        XCTAssertEqual(resolveClose(saved: .quit, prompt: nil), .quit(persist: false))
        XCTAssertEqual(resolveClose(saved: nil, prompt: nil), .stay)
        XCTAssertEqual(
            resolveClose(saved: nil, prompt: ClosePrompt(choice: .tray, remember: true)),
            .tray(persist: true)
        )
        XCTAssertEqual(
            resolveClose(saved: nil, prompt: ClosePrompt(choice: .quit, remember: true)),
            .quit(persist: true)
        )
        XCTAssertEqual(
            resolveClose(saved: nil, prompt: ClosePrompt(choice: .tray, remember: false)),
            .tray(persist: false)
        )
        XCTAssertEqual(
            resolveClose(saved: nil, prompt: ClosePrompt(choice: .quit, remember: false)),
            .quit(persist: false)
        )
        XCTAssertEqual(
            resolveClose(saved: .quit, prompt: ClosePrompt(choice: .tray, remember: true)),
            .quit(persist: false)
        )
        XCTAssertFalse(statusClickOpensMenu(rightButton: false, control: false))
        XCTAssertTrue(statusClickOpensMenu(rightButton: true, control: false))
        XCTAssertTrue(statusClickOpensMenu(rightButton: false, control: true))
        XCTAssertEqual(firstDroppedPath(["  ", "/tmp/a", "/tmp/b"]), "/tmp/a")
        XCTAssertNil(firstDroppedPath([" ", ""]))
    }

    func testPrepareAndExitLabels() {
        XCTAssertTrue(prepareSucceeded("正在启动\nready 127.0.0.1:6016\n"))
        XCTAssertFalse(prepareSucceeded("not-ready 127.0.0.1:6016 没开\n"))
        XCTAssertEqual(batchExitLabel(0), "完成")
        XCTAssertEqual(batchExitLabel(1), "完成，有失败")
        XCTAssertEqual(batchExitLabel(130), "已停止")
        XCTAssertEqual(batchExitLabel(2), "没有开始")
    }

    func testRootAndPythonSelection() {
        let root = findRepositoryRoot(starts: ["/repo/macos/CapsWriterShell/.build/CapsWriter"]) { path in
            path == "/repo"
        }
        XCTAssertEqual(root, "/repo")
        XCTAssertEqual(resolvePython(environment: "/env/python", isExecutable: { $0 == "/env/python" }), "/env/python")
        XCTAssertEqual(resolvePython(environment: nil, isExecutable: { $0 == homebrewPython }), homebrewPython)
        XCTAssertEqual(resolvePython(environment: "missing", isExecutable: { _ in false }), "python3")
    }

    func testFinderPathKeepsSystemEntriesAndFindsHomebrew() {
        let gui = pythonEnvironment(["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/Users/me"]) { path in
            path == "/opt/homebrew/bin"
        }
        XCTAssertEqual(gui["PATH"], "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        XCTAssertEqual(gui["PYTHONUNBUFFERED"], "1")
        XCTAssertEqual(gui["HOME"], "/Users/me")

        let both = pythonEnvironment(["PATH": "/usr/bin:/bin"]) { _ in true }
        XCTAssertEqual(both["PATH"], "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")

        let already = pythonEnvironment(["PATH": "/usr/bin:/opt/homebrew/bin"]) { path in
            path == "/opt/homebrew/bin" || path == "/usr/local/bin"
        }
        XCTAssertEqual(already["PATH"], "/usr/local/bin:/usr/bin:/opt/homebrew/bin")

        let unchanged = pythonEnvironment(["PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "0"]) { _ in false }
        XCTAssertEqual(unchanged["PATH"], "/usr/bin:/bin")
        XCTAssertEqual(unchanged["PYTHONUNBUFFERED"], "1")

        let empty = pythonEnvironment([:]) { path in path == "/usr/local/bin" }
        XCTAssertEqual(empty["PATH"], "/usr/local/bin")
    }

    func testClientSettingsAndShortPunctuation() {
        let text = """
        addr = '127.0.0.1'
        port = '6016'
        threshold    = 0.3
        context = ''
        language = 'auto'
        trash_punc = '，。,.'
        trash_punc_thresh = 8
        mic_seg_duration = 60
        mic_seg_overlap = 4
        udp_control_port = 6018
        """
        let settings = ClientSettings(text: text)
        XCTAssertEqual(settings.port, 6016)
        XCTAssertEqual(settings.threshold, 0.3)
        XCTAssertEqual(settings.language, "auto")
        XCTAssertEqual(settings.segmentDuration, 60)
        XCTAssertEqual(stripTrailingPunctuation("十五个。", marks: settings.trashPunctuation, threshold: 8), "十五个")
        XCTAssertEqual(stripTrailingPunctuation("一二三四五六七八九。", marks: "，。,.", threshold: 8), "一二三四五六七八九。")
    }

    func testDownsampleMatchesEveryThirdFrame() {
        let samples: [Float] = [1, 3, 10, 10, 0, 0, 4, 6, 0, 0, 8, 8]
        let down = toRecognitionRate(samples, channels: 2, sampleRate: 48000)
        XCTAssertEqual(down, [2, 5])
    }

    func testAudioMessageUsesTheServerKeys() throws {
        let json = audioMessageJSON(
            taskID: "abc",
            samples: [1, -1],
            isFinal: false,
            timeStart: 12.5,
            segmentDuration: 60,
            segmentOverlap: 4,
            context: "",
            language: "auto"
        )
        let data = Data(json.utf8)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["task_id"] as? String, "abc")
        XCTAssertEqual(object["source"] as? String, "mic")
        XCTAssertEqual(object["is_final"] as? Bool, false)
        XCTAssertEqual(object["seg_duration"] as? Double, 60)
        XCTAssertEqual(object["language"] as? String, "auto")
        let decoded = Data(base64Encoded: object["data"] as? String ?? "")
        XCTAssertEqual(decoded?.count, 8)
        let parsed = recognitionText(from: #"{"task_id":"abc","is_final":true,"text":"你好"}"#)
        XCTAssertEqual(parsed?.text, "你好")
        XCTAssertEqual(parsed?.isFinal, true)
    }

    func testDictationOutcomesStaySeparateFromTheTranscript() {
        XCTAssertEqual(rightOptionKeyCode, 61)
        XCTAssertEqual(silencePeak, 0.001)
        XCTAssertEqual(classifyDictation(duration: 0.29, threshold: 0.3, peak: 0.4, text: "你好"), .short)
        XCTAssertEqual(classifyDictation(duration: 0.3, threshold: 0.3, peak: 0.0009, text: "你好"), .silent)
        XCTAssertEqual(classifyDictation(duration: 1, threshold: 0.3, peak: 0.001, text: "  "), .empty)
        XCTAssertEqual(classifyDictation(duration: 1, threshold: 0.3, peak: 0.2, text: "你好"), .text)
        XCTAssertEqual(dictationStatus(.short), "按得太短")
        XCTAssertEqual(dictationStatus(.silent), "这段录音是静音")
        XCTAssertEqual(dictationStatus(.empty), "识别结果为空")
        XCTAssertEqual(dictationStatus(.text), "已粘贴")
        XCTAssertFalse(dictationStatus(.text).contains("你好"))
    }

    func testRuntimeLogKeepsTheLineWhenTheFileWriteFails() {
        var log = ShellLog(capacity: 2)
        var writes: [String] = []
        log.record("dictation finished\ndelivered", at: Date(timeIntervalSince1970: 0)) { line in
            writes.append(line)
            return false
        }
        log.record("paste posted", at: Date(timeIntervalSince1970: 1)) { line in
            writes.append(line)
            return false
        }
        log.record("batch finished", at: Date(timeIntervalSince1970: 2)) { line in
            writes.append(line)
            return false
        }
        XCTAssertEqual(log.lines.count, 2)
        XCTAssertFalse(log.lines[0].contains("\n"))
        XCTAssertEqual(writes.count, 3)
        XCTAssertTrue(log.lines.last?.hasSuffix("batch finished") == true)
    }

    func testProgressInsideOneSecondKeepsTheFirstLineOnly() {
        var log = ProgressLog(interval: 30)
        let start = Date(timeIntervalSince1970: 1_700_000_000)
        XCTAssertTrue(log.keep("    发送进度：1.00s", at: start))
        XCTAssertFalse(log.keep("    发送进度：1.20s", at: start.addingTimeInterval(0.2)))
        XCTAssertFalse(log.keep("    发送进度：1.40s", at: start.addingTimeInterval(0.8)))
        XCTAssertTrue(log.keep("找到 1 个音视频，跳过 0 个，待转录 1 个", at: start.addingTimeInterval(0.3)))
        XCTAssertTrue(log.keep("未找到 ffmpeg。文件转录要用它抽出 16kHz 单声道音频", at: start.addingTimeInterval(0.4)))
        XCTAssertTrue(log.keep("    转录进度：1.00s", at: start.addingTimeInterval(0.5)))
        XCTAssertFalse(log.keep("    转录进度：1.40s", at: start.addingTimeInterval(0.9)))
        XCTAssertTrue(log.keep("    转录完成", at: start.addingTimeInterval(1)))
        XCTAssertTrue(log.keep("[1/2] /tmp/a.wav", at: start.addingTimeInterval(1.1)))
        XCTAssertTrue(log.keep("  失败: 音频发送失败", at: start.addingTimeInterval(1.2)))
        XCTAssertTrue(log.keep("[2026-10-28 22:10:44.635]     发送进度：40.00s", at: start.addingTimeInterval(30)))
        XCTAssertFalse(log.keep("    发送进度：40.20s", at: start.addingTimeInterval(30.2)))
    }

    func testBundledRuntimeIsUsedInsteadOfTheSourceTree() {
        let bundle = "/tmp/dist/CapsWriter.app"
        let runtime = bundledRuntimePath(bundle)
        XCTAssertEqual(runtime, "/tmp/dist/CapsWriter.app/Contents/Resources/runtime")
        let found = preferBundledRuntime(bundlePath: bundle) { $0 == runtime }
        XCTAssertEqual(found, runtime)
        XCTAssertNil(preferBundledRuntime(bundlePath: bundle) { _ in false })

        let prepare = prepareLaunch(bundled: true, python: "python3", root: runtime, startServer: false)
        XCTAssertEqual(prepare.executable, runtime + "/batch_transcribe")
        XCTAssertEqual(prepare.arguments, ["--prepare", "--no-start-server"])
        let batch = batchLaunch(bundled: true, python: "python3", root: runtime, arguments: ["/tmp/a.wav", "--model", "sensevoice"])
        XCTAssertEqual(batch.executable, runtime + "/batch_transcribe")
        XCTAssertEqual(batch.arguments, ["/tmp/a.wav", "--model", "sensevoice"])
        let stop = stopLaunch(bundled: true, python: "python3", root: runtime)
        XCTAssertEqual(stop.arguments, ["--stop-background"])

        let source = prepareLaunch(bundled: false, python: "/env/python", root: "/repo", startServer: true)
        XCTAssertEqual(source.executable, "/env/python")
        XCTAssertEqual(source.arguments.first, "-c")
        XCTAssertTrue(source.arguments[1].contains("prepare_server(start=True"))
    }
}
