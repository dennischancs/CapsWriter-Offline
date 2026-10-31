import SwiftUI
import CapsWriterCore

struct BatchWindowView: View {
    @ObservedObject var model: BatchModel
    @State private var dropHover = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            addressRow
            GroupBox("参数") {
                LazyVGrid(
                    columns: [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading)],
                    alignment: .leading,
                    spacing: 6
                ) {
                    toggle("包含子文件夹", $model.recursive, "会进入里面的文件夹。关掉后只看这一层。")
                    toggle("长文件先切开", $model.splitLong, "超过 2 小时先切开再识别，最后仍合并成一个字幕、文本和 json。这个 2 小时是固定的。")
                    toggle("已有字幕也重做", $model.force, "旁边已经写好同名 srt 时平常会跳过，不复写。空的或没写完的会再做。勾上后重新转录。")
                    toggle("包含隐藏文件", $model.hidden, "名字以点开头的文件和文件夹也会处理。")
                    toggle("服务端没开就启动", $model.startServer, "6016 没在听时，由这里拉起旁边的服务端。窗口不会等模型加载完才出现。")
                    toggle("结束后关掉本次启动的服务端", $model.stopServer, "只关掉这一次拉起的服务端。原来就已经开着的不会关。")
                }
                .padding(4)
            }
            toolRow
            actionRow
            lampRow
            logView
        }
        .padding(12)
        .frame(minWidth: 760, minHeight: 520)
    }

    private var addressRow: some View {
        HStack(spacing: 8) {
            Text("地址")
            TextField("", text: $model.target)
                .textFieldStyle(.roundedBorder)
                .help("粘贴路径，或从 Finder 把一个文件、文件夹拖到这里。程序自己判断是文件还是文件夹。")
                .onDrop(of: [.fileURL], isTargeted: $dropHover) { providers in
                    guard let provider = providers.first else { return false }
                    _ = provider.loadObject(ofClass: URL.self) { object, _ in
                        let path = object?.path ?? ""
                        let chosen = firstDroppedPath([path])
                        DispatchQueue.main.async {
                            if let chosen { model.target = chosen }
                        }
                    }
                    return true
                }
            Button("打开", action: browse)
                .help("先选文件夹。取消后再选一个文件。")
        }
    }

    private var toolRow: some View {
        HStack(spacing: 8) {
            Text("模型")
            Picker("", selection: Binding(
                get: { model.model },
                set: { model.selectModel($0) }
            )) {
                ForEach(model.availableModels, id: \.id) { item in
                    Text(item.label).tag(item.id)
                }
            }
            .labelsHidden()
            .frame(width: 250)
            .disabled(model.busy)
            .help("只列出本机 models 里已经放好的模型。放进新目录后点刷新。换了马上写入服务端配置。正在转录时不能换。")
            Button("刷新", action: model.refreshModels)
                .disabled(model.busy)
                .help("重新查看 models 目录，把新放进去的模型加进菜单。")
            Text("日志")
            Picker("", selection: $model.logLevel) {
                ForEach(logLevels, id: \.self) { level in
                    Text(level).tag(level)
                }
            }
            .labelsHidden()
            .frame(width: 120)
            .help("窗口里显示到哪一级。DEBUG 最详细，ERROR 只留错误。发送进度和转录进度各自只占一行，数字从 0、60、120 改到这段音频结束。")
            Spacer()
        }
    }

    private var actionRow: some View {
        HStack(spacing: 8) {
            Button("开始转录", action: model.start)
                .disabled(!model.ready || model.busy)
                .help("绿灯之后才开始。单个文件最多等「时长的 4 倍再加 60 秒」，并且不少于 180 秒。识别完成会马上返回，不会故意等满。")
            Button("停止转录", action: model.stop)
                .disabled(!model.busy)
                .help("马上中断，和命令行 Ctrl+C 一样。已经写好的字幕保留，后面的文件不再开始。再点一次强制结束。")
            Text(model.progressText)
                .font(.system(size: 12, design: .monospaced))
                .help("当前是正在转录的这一份，总计不含跳过的文件。")
            ProgressView(value: model.progressTotal > 0 ? model.progressValue : 0, total: 1)
                .progressViewStyle(.linear)
                .frame(width: 140)
            Text(model.status)
            Spacer()
        }
    }

    private var lampRow: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(lampColor)
                .frame(width: 14, height: 14)
            Text(model.readyText)
                .help("红灯：还没准备好。黄灯：正在等服务端，最多 180 秒。绿灯 Ready：可以开始。这个等待不是识别速度，模型好了就会变绿。")
            Spacer()
        }
    }

    private var logView: some View {
        TerminalLogView(model: model)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .layoutPriority(1)
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color(nsColor: .separatorColor)))
    }

    private var lampColor: Color {
        switch model.lamp {
        case .red:
            return Color(red: 214 / 255, green: 69 / 255, blue: 69 / 255)
        case .yellow:
            return Color(red: 224 / 255, green: 176 / 255, blue: 0)
        case .green:
            return Color(red: 47 / 255, green: 158 / 255, blue: 68 / 255)
        }
    }

    private func toggle(_ title: String, _ value: Binding<Bool>, _ hint: String) -> some View {
        Toggle(title, isOn: value).help(hint)
    }

    private func browse() {
        let folder = NSOpenPanel()
        folder.canChooseFiles = false
        folder.canChooseDirectories = true
        folder.allowsMultipleSelection = false
        folder.prompt = "打开"
        folder.title = "打开文件夹"
        if folder.runModal() == .OK, let url = folder.url {
            model.target = url.path
            return
        }
        let file = NSOpenPanel()
        file.canChooseFiles = true
        file.canChooseDirectories = false
        file.allowsMultipleSelection = false
        file.prompt = "打开"
        file.title = "打开文件"
        if file.runModal() == .OK, let url = file.url {
            model.target = url.path
        }
    }
}

private struct TerminalLogView: NSViewRepresentable {
    @ObservedObject var model: BatchModel

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = TerminalScrollView()
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
        scroll.drawsBackground = true
        scroll.borderType = .noBorder
        scroll.backgroundColor = .textBackgroundColor

        let text = NSTextView()
        text.isEditable = false
        text.isSelectable = true
        text.isRichText = false
        text.drawsBackground = true
        text.backgroundColor = .textBackgroundColor
        text.font = Self.font
        text.textColor = .labelColor
        text.isAutomaticQuoteSubstitutionEnabled = false
        text.isAutomaticDashSubstitutionEnabled = false
        text.isAutomaticTextReplacementEnabled = false
        text.isAutomaticSpellingCorrectionEnabled = false
        text.isContinuousSpellCheckingEnabled = false
        text.isGrammarCheckingEnabled = false
        text.smartInsertDeleteEnabled = false
        text.isVerticallyResizable = true
        text.isHorizontallyResizable = false
        text.autoresizingMask = [.width]
        text.textContainerInset = NSSize(width: 6, height: 6)
        text.textContainer?.widthTracksTextView = true
        text.textContainer?.heightTracksTextView = false
        text.textContainer?.containerSize = NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude)
        text.minSize = NSSize(width: 0, height: 0)
        text.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        text.layoutManager?.allowsNonContiguousLayout = true
        scroll.documentView = text

        model.attachLog { [weak text] edits in
            guard let text, let scroll = text.enclosingScrollView else { return }
            apply(edits, text: text, scroll: scroll)
        }
        return scroll
    }

    func updateNSView(_ nsView: NSScrollView, context: Context) {}

    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
        CGSize(width: finite(proposal.width, fallback: 680), height: finite(proposal.height, fallback: 280))
    }

    private func finite(_ value: CGFloat?, fallback: CGFloat) -> CGFloat {
        guard let value, value.isFinite, value > 0 else { return fallback }
        return value
    }

    private static var font: NSFont {
        NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
    }

    private static var attributes: [NSAttributedString.Key: Any] {
        [.font: font, .foregroundColor: NSColor.labelColor]
    }

    private func apply(_ edits: [LogEdit], text: NSTextView, scroll: NSScrollView) {
        let follow = logShouldFollow(distanceFromBottom: distanceFromBottom(scroll))
        guard let storage = text.textStorage else { return }
        storage.beginEditing()
        for edit in edits {
            switch edit {
            case .reset(let body):
                storage.setAttributedString(NSAttributedString(string: body, attributes: Self.attributes))
            case .append(let row):
                let needsBreak = storage.length > 0 && !text.string.hasSuffix("\n")
                let piece = (needsBreak ? "\n" : "") + row + "\n"
                storage.append(NSAttributedString(string: piece, attributes: Self.attributes))
            case .replace(let kind, let row):
                replaceLast(kind: kind, with: row, in: text, storage: storage)
            }
        }
        storage.endEditing()
        guard follow else { return }
        let length = storage.length
        text.scrollRangeToVisible(NSRange(location: length, length: 0))
    }

    private func replaceLast(kind: String, with line: String, in text: NSTextView, storage: NSTextStorage) {
        let marker = kind == "send" ? "发送进度" : "转录进度"
        let current = text.string as NSString
        let found = current.range(of: marker, options: .backwards)
        let replacement = NSAttributedString(string: line, attributes: Self.attributes)
        guard found.location != NSNotFound else {
            let needsBreak = storage.length > 0 && !text.string.hasSuffix("\n")
            storage.append(NSAttributedString(string: (needsBreak ? "\n" : "") + line + "\n", attributes: Self.attributes))
            return
        }
        let before = found.location == 0
            ? NSNotFound
            : current.range(of: "\n", options: .backwards, range: NSRange(location: 0, length: found.location)).location
        let start = before == NSNotFound ? 0 : before + 1
        let ending = current.range(
            of: "\n",
            options: [],
            range: NSRange(location: found.location, length: current.length - found.location)
        )
        let end = ending.location == NSNotFound ? current.length : ending.location
        storage.replaceCharacters(in: NSRange(location: start, length: end - start), with: replacement)
    }

    private func distanceFromBottom(_ scroll: NSScrollView) -> Double {
        guard let document = scroll.documentView else { return 0 }
        let visible = scroll.contentView.bounds
        return Double(max(0, document.frame.maxY - visible.maxY))
    }
}

private final class TerminalScrollView: NSScrollView {
    override var intrinsicContentSize: NSSize {
        NSSize(width: NSView.noIntrinsicMetric, height: NSView.noIntrinsicMetric)
    }
}
