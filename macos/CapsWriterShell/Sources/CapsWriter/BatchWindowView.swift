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
                    toggle("已有字幕也重做", $model.force, "旁边已经有同名 srt 时平常会跳过。勾上后重新转录。")
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
            Picker("", selection: $model.model) {
                ForEach(modelChoices, id: \.id) { item in
                    Text(item.label).tag(item.id)
                }
            }
            .labelsHidden()
            .frame(width: 180)
            .disabled(model.busy)
            .help("下次开始前写入配置并重启服务端。正在转录时不能换。")
            Text("日志")
            Picker("", selection: $model.logLevel) {
                ForEach(logLevels, id: \.self) { level in
                    Text(level).tag(level)
                }
            }
            .labelsHidden()
            .frame(width: 120)
            .help("窗口里显示到哪一级。DEBUG 最详细，ERROR 只留错误。发送进度和转录进度至少隔 30 秒一行。")
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
                .help("当前这段做完就停。已经写好的字幕保留，后面的文件不再开始。")
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
        ScrollView {
            Text(model.log.isEmpty ? " " : model.log)
                .font(.system(size: 12, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
        .background(Color(nsColor: .textBackgroundColor))
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
