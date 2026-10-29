import AppKit
import SwiftUI
import CapsWriterCore

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate {
    private var status: NSStatusItem!
    private var statusMenu: NSMenu!
    private var appMenu: NSMenu!
    private var window: NSWindow!
    private var model: BatchModel!
    private var dictation: DictationController!
    private var store: ConfigStore!
    private var shellLog = ShellLog()
    private var quitting = false
    private var dictationStatus = "按住右 Option"

    func applicationDidFinishLaunching(_ notification: Notification) {
        model = BatchModel()
        model.note = { [weak self] kind in
            Task { @MainActor in self?.note(kind) }
        }
        store = ConfigStore(root: model.root, python: model.python)
        store.note = { [weak self] kind in
            Task { @MainActor in self?.note(kind) }
        }
        model.onConfigurationChanged = { [weak self] in
            self?.store.reload()
        }
        store.load()
        dictation = DictationController()
        dictation.note = { [weak self] kind in
            Task { @MainActor in self?.note(kind) }
        }
        dictation.settings = { [weak self] in
            self?.model.clientSettings() ?? ClientSettings()
        }
        dictation.onStatus = { [weak self] text in
            DispatchQueue.main.async { self?.dictationStatus = text }
        }
        buildStatusItem()
        buildMainMenu()
        installIcon()
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        model.beginPrepare()
        Permissions.promptAll()
        dictation.startMonitoring()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        quitting = true
        model.stop()
        model.stopBackground {
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        let saved = readChoice()
        let prompt = saved == nil ? askChoice() : nil
        switch resolveClose(saved: saved, prompt: prompt) {
        case .tray(let persist):
            if persist { writeChoice(.tray) }
            hideToMenu()
            note(persist ? "close remembered tray" : "close tray")
        case .quit(let persist):
            if persist { writeChoice(.quit) }
            note(persist ? "close remembered quit" : "close quit")
            NSApp.terminate(nil)
        case .stay:
            break
        }
        return false
    }

    func menuWillOpen(_ menu: NSMenu) {
        if menu === appMenu {
            for entry in menu.items where entry.action == #selector(forgetCloseChoice) {
                entry.isEnabled = readChoice() != nil
            }
            return
        }
        guard menu === statusMenu else { return }
        menu.removeAllItems()
        menu.addItem(item("显示批量转录", #selector(showWindow)))
        menu.addItem(item("关于 CapsWriter", #selector(showAbout)))
        menu.addItem(.separator())
        menu.addItem(item("听写：\(dictationStatus)", nil))
        menu.addItem(item("麦克风：\(Permissions.microphoneAllowed() ? "已允许" : "未允许")", nil))
        menu.addItem(item("辅助功能：\(Permissions.accessibilityAllowed() ? "已允许" : "未允许")", nil))
        menu.addItem(item("输入监控：\(Permissions.listenAllowed() ? "已允许" : "未允许")", nil))
        menu.addItem(.separator())
        menu.addItem(item("打开日志目录", #selector(openLogs)))
        menu.addItem(item("打开热词文件", #selector(openHotwords)))
        let forget = item("下次关闭再询问", #selector(forgetCloseChoice))
        forget.isEnabled = readChoice() != nil
        menu.addItem(forget)
        menu.addItem(.separator())
        menu.addItem(item("退出", #selector(quit)))
    }

    private func buildStatusItem() {
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusMenu = NSMenu()
        statusMenu.delegate = self
        if let button = status.button {
            button.image = menuBarImage()
            button.imagePosition = .imageOnly
            button.toolTip = "CapsWriter"
            button.target = self
            button.action = #selector(statusClicked(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
        NSEvent.addLocalMonitorForEvents(matching: [.rightMouseUp]) { [weak self] event in
            guard let self, let button = self.status.button, event.window === button.window else { return event }
            let point = button.convert(event.locationInWindow, from: nil)
            if button.bounds.contains(point) {
                self.openStatusMenu()
                return nil
            }
            return event
        }
    }

    private func buildMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        main.addItem(appItem)
        appMenu = NSMenu(title: "CapsWriter")
        appMenu.delegate = self
        appItem.submenu = appMenu
        appMenu.addItem(item("关于 CapsWriter", #selector(showAbout)))
        appMenu.addItem(.separator())
        appMenu.addItem(item("下次关闭再询问", #selector(forgetCloseChoice)))
        appMenu.addItem(.separator())
        let quitItem = item("退出 CapsWriter", #selector(quit))
        quitItem.keyEquivalent = "q"
        appMenu.addItem(quitItem)

        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "编辑")
        editItem.submenu = edit
        addEdit(edit, "撤销", Selector(("undo:")), "z")
        addEdit(edit, "重做", Selector(("redo:")), "Z")
        edit.addItem(.separator())
        addEdit(edit, "剪切", #selector(NSText.cut(_:)), "x")
        addEdit(edit, "复制", #selector(NSText.copy(_:)), "c")
        addEdit(edit, "粘贴", #selector(NSText.paste(_:)), "v")
        addEdit(edit, "全选", #selector(NSText.selectAll(_:)), "a")
        NSApp.mainMenu = main
    }

    private func buildWindow() {
        let host = NSHostingController(rootView: RootView(model: model, store: store))
        window = NSWindow(contentViewController: host)
        window.title = "CapsWriter"
        window.setContentSize(NSSize(width: 860, height: 620))
        window.minSize = NSSize(width: 760, height: 520)
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.center()
    }

    @objc private func statusClicked(_ sender: Any?) {
        let event = NSApp.currentEvent
        let right = event?.type == .rightMouseUp
        let control = event?.modifierFlags.contains(.control) == true
        if statusClickOpensMenu(rightButton: right, control: control) {
            openStatusMenu()
        } else {
            showWindow()
        }
    }

    private func openStatusMenu() {
        guard let button = status.button else { return }
        statusMenu.popUp(positioning: nil, at: NSPoint(x: 0, y: button.bounds.height), in: button)
    }

    @objc private func showAbout() {
        NSApp.activate(ignoringOtherApps: true)
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        var options: [NSApplication.AboutPanelOptionKey: Any] = [
            .applicationName: "CapsWriter",
            .credits: NSAttributedString(string: "离线听写。识别由这个 App 里的 start_server 完成。"),
        ]
        if !version.isEmpty {
            options[.applicationVersion] = version
        }
        if let icon = NSApp.applicationIconImage {
            options[.applicationIcon] = icon
        }
        NSApp.orderFrontStandardAboutPanel(options: options)
    }

    @objc private func forgetCloseChoice() {
        guard let url = choiceURL() else { return }
        try? FileManager.default.removeItem(at: url)
        note("close choice cleared")
    }

    @objc private func showWindow() {
        NSApp.setActivationPolicy(.regular)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openLogs() {
        guard let root = model.root else { return }
        let url = URL(fileURLWithPath: root).appendingPathComponent("logs")
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        NSWorkspace.shared.open(url)
    }

    @objc private func openHotwords() {
        guard let root = model.root else { return }
        let url = URL(fileURLWithPath: root).appendingPathComponent("hot.txt")
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        NSWorkspace.shared.open(url)
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func hideToMenu() {
        window.orderOut(nil)
        NSApp.setActivationPolicy(.accessory)
    }

    private func askChoice() -> ClosePrompt? {
        let alert = NSAlert()
        alert.messageText = "关闭 CapsWriter"
        alert.informativeText = "缩小到菜单栏，或退出并结束后台服务。"
        alert.addButton(withTitle: "缩小到菜单栏")
        alert.addButton(withTitle: "退出")
        alert.addButton(withTitle: "取消")
        if alert.buttons.count > 2 {
            alert.buttons[2].keyEquivalent = "\u{1b}"
        }
        let remember = NSButton(checkboxWithTitle: "记住我的选择", target: nil, action: nil)
        remember.state = .on
        remember.frame = NSRect(x: 0, y: 0, width: 240, height: 22)
        let box = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        box.addSubview(remember)
        alert.accessoryView = box
        let response = alert.runModal()
        let choice: CloseChoice
        if response == .alertFirstButtonReturn {
            choice = .tray
        } else if response == .alertSecondButtonReturn {
            choice = .quit
        } else {
            return nil
        }
        return ClosePrompt(choice: choice, remember: remember.state == .on)
    }

    private func installIcon() {
        guard let image = bundledIcon() else { return }
        NSApp.applicationIconImage = image
    }

    private func bundledIcon() -> NSImage? {
        if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let image = NSImage(contentsOf: url) {
            return image
        }
        let resource = Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/AppIcon.icns")
        return NSImage(contentsOf: resource)
    }

    private func menuBarImage() -> NSImage {
        let side: CGFloat = 18
        let image = NSImage(size: NSSize(width: side, height: side), flipped: false) { rect in
            let text = "Cw" as NSString
            let font = NSFont.systemFont(ofSize: 9, weight: .bold)
            let attrs: [NSAttributedString.Key: Any] = [
                .font: font,
                .foregroundColor: NSColor.black,
            ]
            let size = text.size(withAttributes: attrs)
            let origin = NSPoint(
                x: (rect.width - size.width) / 2,
                y: (rect.height - size.height) / 2
            )
            text.draw(at: origin, withAttributes: attrs)
            return true
        }
        image.isTemplate = true
        return image
    }

    private func addEdit(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String) {
        menu.addItem(NSMenuItem(title: title, action: action, keyEquivalent: key))
    }

    private func choiceURL() -> URL? {
        guard let root = model.root else { return nil }
        return URL(fileURLWithPath: root).appendingPathComponent("logs/batch_window_close.txt")
    }

    private func readChoice() -> CloseChoice? {
        guard let url = choiceURL() else { return nil }
        let text = try? String(contentsOf: url, encoding: .utf8)
        return readCloseChoice(text)
    }

    private func writeChoice(_ choice: CloseChoice) {
        guard let url = choiceURL() else { return }
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let temporary = url.appendingPathExtension("partial")
        do {
            try (choice.rawValue + "\n").write(to: temporary, atomically: true, encoding: .utf8)
            _ = try FileManager.default.replaceItemAt(url, withItemAt: temporary)
        } catch {
            return
        }
    }

    private func note(_ kind: String) {
        shellLog.record(kind, at: Date()) { line in
            guard let root = self.model.root else { return false }
            let url = URL(fileURLWithPath: root).appendingPathComponent("logs/shell.log")
            do {
                try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
                if !FileManager.default.fileExists(atPath: url.path) {
                    FileManager.default.createFile(atPath: url.path, contents: nil)
                }
                let handle = try FileHandle(forWritingTo: url)
                defer { try? handle.close() }
                try handle.seekToEnd()
                try handle.write(contentsOf: Data((line + "\n").utf8))
                return true
            } catch {
                return false
            }
        }
    }

    private func item(_ title: String, _ action: Selector?) -> NSMenuItem {
        let entry = NSMenuItem(title: title, action: action, keyEquivalent: "")
        entry.target = self
        if action == nil { entry.isEnabled = false }
        return entry
    }
}

@main
enum CapsWriterMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }
}
