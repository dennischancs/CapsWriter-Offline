import AppKit
import SwiftUI

struct RootView: View {
    @ObservedObject var model: BatchModel
    @ObservedObject var store: ConfigStore
    @State private var tab = 0

    var body: some View {
        TabView(selection: $tab) {
            BatchWindowView(model: model)
                .tabItem { Text("批量转换") }
                .tag(0)
            SettingsPage(store: store, page: "client")
                .tabItem { Text("client") }
                .tag(1)
            SettingsPage(store: store, page: "server")
                .tabItem { Text("server") }
                .tag(2)
        }
        .frame(minWidth: 760, minHeight: 520)
    }
}

struct SettingsPage: View {
    @ObservedObject var store: ConfigStore
    let page: String
    @State private var texts: [String: String] = [:]
    @State private var flags: [String: Bool] = [:]
    @State private var blocks: [String: String] = [:]
    @State private var shown = ""

    var body: some View {
        let current = store.page(page)
        let token = revisionToken(current)
        Group {
            if !store.loaded {
                ProgressView("正在读取配置")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let message = store.loadError {
                Text(message)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .padding(12)
            } else {
                form(current)
            }
        }
        .onChange(of: token) { value in
            guard value != shown else { return }
            texts = [:]
            flags = [:]
            blocks = [:]
            shown = value
        }
    }

    private func revisionToken(_ current: SettingPage) -> String {
        current.summary.joined(separator: "\n") + "\n" + current.sections.map { section in
            section.fields.map { field in
                [
                    field.id,
                    field.text,
                    field.boolValue ? "1" : "0",
                    field.lines.joined(separator: "|"),
                    field.pairs.map { $0.joined(separator: "=") }.joined(separator: "|"),
                ].joined(separator: "\t")
            }.joined(separator: "\n")
        }.joined(separator: "\n")
    }

    private func form(_ current: SettingPage) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("现在这样跑") {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(current.summary.enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        HStack(spacing: 8) {
                            Button("写入配置") { save(current) }
                                .disabled(store.saving)
                            Text(store.status)
                                .foregroundStyle(.secondary)
                            Spacer()
                        }
                    }
                    .padding(4)
                }
                ForEach(current.sections) { section in
                    GroupBox(section.title) {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(section.fields) { field in
                                row(field)
                            }
                        }
                        .padding(4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                GroupBox("日志") {
                    ScrollView {
                        Text(page == "server" ? store.serverLog : store.clientLog)
                            .font(.system(size: 12, design: .monospaced))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }
                    .frame(height: 160)
                }
            }
            .padding(12)
        }
    }

    @ViewBuilder
    private func row(_ field: SettingField) -> some View {
        let locked = field.recommended && !store.unlocked.contains(field.id)
        if field.kind == "bool" {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                label(field, locked: locked)
                Toggle("", isOn: flagBinding(field))
                    .labelsHidden()
                    .disabled(locked)
                    .help(field.help)
                Spacer()
            }
            .overlay(lockCover(field, locked: locked))
        } else if field.kind == "lines" || field.kind == "pairs" {
            VStack(alignment: .leading, spacing: 4) {
                label(field, locked: locked)
                TextEditor(text: blockBinding(field))
                    .font(.system(size: 12, design: .monospaced))
                    .frame(minHeight: 64)
                    .disabled(locked)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(nsColor: .separatorColor))
                    )
                    .overlay(lockCover(field, locked: locked))
                    .help(field.help)
            }
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                label(field, locked: locked)
                TextField("", text: textBinding(field))
                    .textFieldStyle(.roundedBorder)
                    .disabled(locked)
                    .help(field.help)
                    .overlay(lockCover(field, locked: locked))
            }
        }
    }

    private func label(_ field: SettingField, locked: Bool) -> some View {
        Text(field.label)
            .frame(width: 230, alignment: .leading)
            .foregroundStyle(locked ? .secondary : .primary)
            .help(field.help)
            .onTapGesture(count: 2) {
                guard field.recommended, !store.unlocked.contains(field.id) else { return }
                confirm(field.id)
            }
    }

    @ViewBuilder
    private func lockCover(_ field: SettingField, locked: Bool) -> some View {
        if locked {
            Color.white.opacity(0.001)
                .contentShape(Rectangle())
                .help(field.help)
                .onTapGesture(count: 2) { confirm(field.id) }
        }
    }

    private func confirm(_ id: String) {
        let alert = NSAlert()
        alert.messageText = "这是推荐值。确定要修改吗？"
        alert.addButton(withTitle: "修改")
        alert.addButton(withTitle: "取消")
        if alert.runModal() == .alertFirstButtonReturn {
            store.unlock(id)
        }
    }

    private func flagBinding(_ field: SettingField) -> Binding<Bool> {
        Binding(
            get: { flags[field.id] ?? field.boolValue },
            set: { flags[field.id] = $0 }
        )
    }

    private func textBinding(_ field: SettingField) -> Binding<String> {
        Binding(
            get: { texts[field.id] ?? field.text },
            set: { texts[field.id] = $0 }
        )
    }

    private func blockBinding(_ field: SettingField) -> Binding<String> {
        Binding(
            get: {
                if let existing = blocks[field.id] { return existing }
                if field.kind == "pairs" {
                    return field.pairs.map { $0.joined(separator: ", ") }.joined(separator: "\n")
                }
                return field.lines.joined(separator: "\n")
            },
            set: { blocks[field.id] = $0 }
        )
    }

    private func save(_ current: SettingPage) {
        var updates: [[String: Any]] = []
        for section in current.sections {
            for field in section.fields {
                if field.recommended && !store.unlocked.contains(field.id) { continue }
                switch field.kind {
                case "bool":
                    let value = flags[field.id] ?? field.boolValue
                    if value != field.boolValue {
                        updates.append(["id": field.id, "value": value])
                    }
                case "lines":
                    let raw = blocks[field.id] ?? field.lines.joined(separator: "\n")
                    let rows = raw
                        .split(whereSeparator: \.isNewline)
                        .map { $0.trimmingCharacters(in: .whitespaces) }
                        .filter { !$0.isEmpty }
                    if rows != field.lines {
                        updates.append(["id": field.id, "value": rows])
                    }
                case "pairs":
                    let raw = blocks[field.id] ?? field.pairs.map { $0.joined(separator: ", ") }.joined(separator: "\n")
                    var rows: [[String]] = []
                    for lineSub in raw.split(whereSeparator: \.isNewline) {
                        let line = lineSub.trimmingCharacters(in: .whitespaces)
                        if line.isEmpty { continue }
                        guard let comma = line.firstIndex(of: ",") else {
                            store.status = "每一行要写成「左边, 右边」"
                            return
                        }
                        let left = line[..<comma].trimmingCharacters(in: .whitespaces)
                        let right = line[line.index(after: comma)...].trimmingCharacters(in: .whitespaces)
                        if left.isEmpty || right.isEmpty {
                            store.status = "每一行要写成「左边, 右边」"
                            return
                        }
                        rows.append([left, right])
                    }
                    if rows != field.pairs {
                        updates.append(["id": field.id, "value": rows])
                    }
                default:
                    let value = texts[field.id] ?? field.text
                    if value != field.text {
                        updates.append(["id": field.id, "value": value])
                    }
                }
            }
        }
        store.save(updates: updates, page: page)
    }
}
