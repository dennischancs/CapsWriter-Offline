# coding: utf-8
"""把 config_client.py / config_server.py 里的赋值读成表单，并按项写回。"""
import ast
import json
import sys
from pathlib import Path


PROJECT_URL = 'https://github.com/HaujetZhao/CapsWriter-Offline'

CLIENT_CLASSES = ('ClientConfig',)
SERVER_CLASSES = (
    'ServerConfig',
    'ModelDownloadLinks',
    'ModelPaths',
    'ParaformerArgs',
    'SenseVoiceArgs',
    'FunASRNanoGGUFArgs',
    'Qwen3ASRGGUFArgs',
    'ForceAlignerGGUFArgs',
)

CLIENT_SECTION = {
    'addr': '连接',
    'port': '连接',
    'shortcuts': '快捷键',
    'darwin_shortcuts': '快捷键',
    'threshold': '快捷键',
    'paste': '输出',
    'darwin_paste': '输出',
    'restore_clip': '输出',
    'paste_apps': '输出',
    'enter_apps': '输出',
    'trash_punc': '输出',
    'trash_punc_thresh': '输出',
    'trash_punc_apps': '输出',
    'traditional_convert': '输出',
    'traditional_locale': '输出',
    'save_audio': '录音',
    'audio_name_len': '录音',
    'context': '识别',
    'language': '识别',
    'hot': '热词和 LLM',
    'hot_thresh': '热词和 LLM',
    'hot_similar': '热词和 LLM',
    'hot_rule': '热词和 LLM',
    'llm_enabled': '热词和 LLM',
    'llm_stop_key': '热词和 LLM',
    'enable_tray': '托盘和日志',
    'log_level': '托盘和日志',
    'mic_seg_duration': '分段和保存',
    'mic_seg_overlap': '分段和保存',
    'file_seg_duration': '分段和保存',
    'file_seg_overlap': '分段和保存',
    'file_save_srt': '分段和保存',
    'file_save_txt': '分段和保存',
    'file_save_json': '分段和保存',
    'file_save_merge': '分段和保存',
    'udp_broadcast': 'UDP',
    'udp_broadcast_targets': 'UDP',
    'udp_control': 'UDP',
    'udp_control_addr': 'UDP',
    'udp_control_port': 'UDP',
}

SERVER_SECTION = {
    'addr': '服务',
    'port': '服务',
    'enable_tray': '服务',
    'log_level': '服务',
    'hotwords_path': '服务',
    'model_type': '模型',
    'model_backend': '模型',
    'qwen_mlx_variant': '模型',
    'mlx_auto_download': '模型',
    'format_num': '模型',
    'format_spell': '模型',
    'aligner_idle_timeout': '显卡',
    'gpu_boost_enabled': '显卡',
    'gpu_boost_cmd': '显卡',
    'gpu_unboost_cmd': '显卡',
    'gpu_unboost_timeout': '显卡',
}

CLASS_SECTION = {
    'ModelDownloadLinks': '下载',
    'ModelPaths': '模型路径',
    'ParaformerArgs': 'Paraformer',
    'SenseVoiceArgs': 'SenseVoice',
    'FunASRNanoGGUFArgs': 'Fun-ASR',
    'Qwen3ASRGGUFArgs': 'Qwen3',
    'ForceAlignerGGUFArgs': '对齐器',
}

CLIENT_ORDER = (
    '连接', '快捷键', '输出', '录音', '识别', '热词和 LLM', '托盘和日志', '分段和保存', 'UDP',
)
SERVER_ORDER = (
    '服务', '模型', '显卡', '下载', '模型路径', 'Paraformer', 'SenseVoice', 'Fun-ASR', 'Qwen3', '对齐器',
)

CLIENT_RECOMMENDED = {
    'threshold', 'audio_name_len', 'trash_punc', 'trash_punc_thresh',
    'hot_thresh', 'hot_similar',
    'mic_seg_duration', 'mic_seg_overlap', 'file_seg_duration', 'file_seg_overlap',
    'file_save_srt', 'file_save_txt', 'file_save_json',
}
SHORTCUT_RECOMMENDED = {'suppress', 'hold_mode'}
SERVER_RECOMMENDED = {
    'aligner_idle_timeout', 'gpu_boost_cmd', 'gpu_unboost_cmd', 'gpu_unboost_timeout',
}
ARGS_EDITABLE = {
    ('SenseVoiceArgs', 'itn'),
    ('FunASRNanoGGUFArgs', 'llm_use_gpu'),
    ('Qwen3ASRGGUFArgs', 'llm_use_gpu'),
    ('ForceAlignerGGUFArgs', 'llm_use_gpu'),
}

KEY_LABELS = {
    'alt_r': '右 Option',
    'alt_gr': '右 Option',
    'alt_l': '左 Option',
}


class ConfigError(ValueError):
    pass


def load_form(root, platform_name=None, memory=None):
    """读两个配置文件，返回 client / server 两个页面。"""
    root = Path(root)
    client_text = (root / 'config_client.py').read_text(encoding='utf-8')
    server_text = (root / 'config_server.py').read_text(encoding='utf-8')
    client_fields = collect_fields(client_text, CLIENT_CLASSES)
    server_fields = collect_fields(server_text, SERVER_CLASSES)
    version = read_version(client_text)
    platform_name = sys.platform if platform_name is None else platform_name
    return {
        'version': version,
        'client': {
            'summary': client_summary(client_fields, root, version, platform_name),
            'sections': group_sections(client_fields, CLIENT_ORDER),
        },
        'server': {
            'summary': server_summary(server_fields, root, version, memory),
            'sections': group_sections(server_fields, SERVER_ORDER),
        },
    }


def apply_text(text, updates):
    """按 id 改这一份配置文本。注释留在原处。"""
    updated = text
    for item in updates:
        updated = apply_one(updated, item['id'], item.get('value'))
    return updated


def apply_files(root, updates):
    """客户端的项写入 config_client.py，其余写入 config_server.py。"""
    root = Path(root)
    client_updates = []
    server_updates = []
    for item in updates:
        field_id = item['id']
        if field_id.startswith('ClientConfig.'):
            client_updates.append(item)
        else:
            server_updates.append(item)
    _write_updates(root / 'config_client.py', client_updates)
    _write_updates(root / 'config_server.py', server_updates)
    return len(updates)


def collect_fields(text, classes):
    tree = ast.parse(text)
    env = {}
    fields = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in classes:
            continue
        class_env = {}
        for item in node.body:
            target = _assignment_name(item)
            if target is None:
                continue
            value = item.value
            kind = classify(value)
            if kind is None:
                raise ConfigError('不能识别 %s.%s' % (node.name, target))
            evaluated = _try_eval(value, class_env, env)
            class_env[target] = evaluated
            env['%s.%s' % (node.name, target)] = evaluated
            if kind == 'shortcuts':
                fields.extend(_shortcut_fields(node.name, target, value))
                continue
            fields.append(_field(text, node.name, target, value, kind, evaluated))
    return fields


def group_sections(fields, order):
    buckets = {name: [] for name in order}
    unknown = []
    for field in fields:
        title = field['section']
        if title in buckets:
            buckets[title].append(field)
        else:
            unknown.append(field)
    sections = []
    for title in order:
        items = buckets[title]
        if title == '快捷键':
            head = [item for item in items if item['id'].endswith('threshold')]
            tail = [item for item in items if item not in head]
            items = head + tail
        if items:
            sections.append({'title': title, 'fields': [_public(item) for item in items]})
    if unknown:
        sections.append({'title': '其它', 'fields': [_public(item) for item in unknown]})
    return sections


def client_summary(fields, root, version, platform_name):
    values = _index(fields)
    addr = values['ClientConfig.addr']['text']
    port = values['ClientConfig.port']['text']
    if platform_name == 'darwin':
        keys = _shortcut_label(fields, 'ClientConfig.darwin_shortcuts')
        paste = values['ClientConfig.darwin_paste']['value']
    else:
        keys = _shortcut_label(fields, 'ClientConfig.shortcuts')
        paste = values['ClientConfig.paste']['value']
    return [
        '版本：%s' % version,
        '项目地址：%s' % PROJECT_URL,
        '当前基文件夹：%s' % Path(root),
        '服务端地址：%s:%s' % (addr, port),
        '当前所用快捷键：%s' % keys,
        '按住快捷键说话，松开即输入。',
        '粘贴：%s' % _on_off(paste),
        '热词：%s' % _on_off(values['ClientConfig.hot']['value']),
        'LLM：%s' % _on_off(values['ClientConfig.llm_enabled']['value']),
        '日志级别：%s' % values['ClientConfig.log_level']['text'],
        '这里改的是 config_client.py，下次启动客户端才生效。',
    ]


def server_summary(fields, root, version, memory=None):
    values = _index(fields)
    engine = values['ServerConfig.model_type']['text']
    variant = values['ServerConfig.qwen_mlx_variant']['text']
    shown_engine, shown_variant = shown_server_model(engine, variant, memory)
    return [
        '版本：%s' % version,
        '项目地址：%s' % PROJECT_URL,
        '当前基文件夹：%s' % Path(root),
        '绑定的服务地址：%s:%s' % (
            values['ServerConfig.addr']['text'],
            values['ServerConfig.port']['text'],
        ),
        '模型：%s' % shown_engine,
        '后端：%s' % values['ServerConfig.model_backend']['text'],
        'Qwen 规格：%s' % shown_variant,
        '托盘：%s' % _on_off(values['ServerConfig.enable_tray']['value']),
        '日志级别：%s' % values['ServerConfig.log_level']['text'],
        '这里改的是 config_server.py，下次启动服务端才生效。',
    ]


def _qwen_selector():
    """只载入规格选择。打包后的 batch_transcribe 是可执行文件，不能当模块导入。"""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / 'server' / 'engines' / 'mlx' / 'variant.py'
    spec = importlib.util.spec_from_file_location('qwen_mlx_variant', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _memory_bytes(memory, fallback):
    if memory is not None:
        return int(memory)
    try:
        import psutil
        return int(psutil.virtual_memory().total)
    except Exception:
        return fallback


def shown_server_model(engine, variant, memory=None):
    """和批量菜单用同一套算法。auto 展开成将要加载的 1.7b 或 0.6b。"""
    selector = _qwen_selector()
    explicit = tuple(selector.QWEN_VARIANTS)
    engines = ('sensevoice', 'fun_asr_nano', 'qwen_asr', 'paraformer')
    if engine == 'qwen_asr':
        if variant in explicit:
            return 'qwen_asr', variant
        selector = _qwen_selector()
        size, _repo, _dirname = selector.select_qwen_variant(
            variant or 'auto',
            _memory_bytes(memory, selector.MEMORY_16GB),
        )
        return 'qwen_asr', size
    if engine in engines:
        return engine, variant
    return 'sensevoice', variant


def classify(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return 'bool'
        if isinstance(node.value, int):
            return 'int'
        if isinstance(node.value, float):
            return 'float'
        if isinstance(node.value, str):
            return 'str'
        if node.value is None:
            return 'none'
        return None
    if isinstance(node, ast.List):
        if not node.elts:
            return 'lines'
        first = node.elts[0]
        if isinstance(first, ast.Dict):
            return 'shortcuts'
        if isinstance(first, ast.Tuple):
            return 'pairs'
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return 'lines'
        return None
    if _is_path(node):
        return 'path'
    if _is_derived(node):
        return 'str'
    return None


def apply_one(text, field_id, value):
    tree = ast.parse(text)
    node = _find_node(tree, field_id)
    if node is None:
        raise ConfigError('没有这项：%s' % field_id)
    kind = classify(node)
    if kind == 'lines':
        return _apply_lines(text, node, value)
    if kind == 'pairs':
        return _apply_pairs(text, node, value)
    if kind == 'shortcuts':
        raise ConfigError('快捷键要改里面的每一项：%s' % field_id)
    replacement = _render_scalar(node, value)
    return replace_span(text, node, replacement)


def _apply_lines(text, node, value):
    rows = _string_rows(value)
    if len(rows) == len(node.elts) and all(isinstance(item, ast.Constant) for item in node.elts):
        pairs = [(item, repr(row)) for item, row in zip(node.elts, rows)]
        return replace_many(text, pairs)
    body = ',\n'.join('        %s' % repr(row) for row in rows)
    rendered = '[\n%s,\n    ]' % body if rows else '[]'
    return replace_span(text, node, rendered)


def _apply_pairs(text, node, value):
    rows = _pair_rows(value)
    if len(rows) == len(node.elts) and all(isinstance(item, ast.Tuple) and len(item.elts) == 2 for item in node.elts):
        pairs = []
        for item, (left, right) in zip(node.elts, rows):
            rendered = '(%s, %s)' % (repr(left), _render_pair_right(item.elts[1], right))
            pairs.append((item, rendered))
        return replace_many(text, pairs)
    sample = None
    for item in node.elts:
        if isinstance(item, ast.Tuple) and len(item.elts) == 2:
            sample = item.elts[1]
            break
    lines = []
    for left, right in rows:
        lines.append('        (%s, %s),' % (repr(left), _render_pair_right(sample, right)))
    rendered = '[\n%s\n    ]' % '\n'.join(lines) if lines else '[]'
    return replace_span(text, node, rendered)


def _render_scalar(node, value):
    kind = classify(node)
    if _is_path(node):
        text = '' if value is None else str(value).strip()
        return 'Path(%s)' % repr(text)
    if kind == 'bool':
        return 'True' if _as_bool(value) else 'False'
    if kind == 'int':
        return str(_as_int(value))
    if kind == 'float':
        return repr(_as_float(value))
    if kind == 'none':
        return _render_optional(value)
    if kind == 'str':
        return repr('' if value is None else str(value))
    raise ConfigError('这项不能这样改')


def _render_optional(value):
    if value is None:
        return 'None'
    text = str(value).strip()
    if text == '' or text.lower() == 'none':
        return 'None'
    if any(mark in text for mark in ('.', 'e', 'E')):
        return repr(float(text))
    return str(int(text, 10))


def _render_pair_right(node, text):
    if isinstance(node, ast.Constant) and isinstance(node.value, float):
        return repr(float(str(text).strip()))
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        raw = str(text).strip()
        if any(mark in raw for mark in ('.', 'e', 'E')):
            return repr(float(raw))
        return str(int(raw, 10))
    return repr(str(text).strip())


def _string_rows(value):
    if isinstance(value, str):
        rows = value.splitlines()
    elif isinstance(value, (list, tuple)):
        rows = [str(item) for item in value]
    else:
        raise ConfigError('列表要一行一个')
    return [row.strip() for row in rows if str(row).strip()]


def _pair_rows(value):
    if not isinstance(value, (list, tuple)):
        raise ConfigError('每一行要写成「左边, 右边」')
    rows = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            left, right = str(item[0]).strip(), str(item[1]).strip()
        elif isinstance(item, str):
            if ',' not in item:
                raise ConfigError('每一行要写成「左边, 右边」')
            left, right = item.split(',', 1)
            left, right = left.strip(), right.strip()
        else:
            raise ConfigError('每一行要写成「左边, 右边」')
        if not left and not right:
            continue
        if not left or right == '':
            raise ConfigError('每一行要写成「左边, 右边」')
        rows.append((left, right))
    return rows


def _as_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ('true', '1', 'yes', 'on'):
        return True
    if text in ('false', '0', 'no', 'off'):
        return False
    raise ConfigError('要填 True 或 False')


def _as_int(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise ConfigError('这里要填整数')
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip(), 10)
    except ValueError as exc:
        raise ConfigError('这里要填整数') from exc


def _as_float(value):
    if isinstance(value, bool):
        raise ConfigError('这里要填数字')
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ConfigError('这里要填数字') from exc


def _field(text, class_name, name, node, kind, evaluated):
    recommended = _recommended(class_name, name, None)
    field = {
        'id': '%s.%s' % (class_name, name),
        'label': name,
        'section': _section(class_name, name),
        'kind': 'str' if _is_derived(node) else kind,
        'help': _help(class_name, name, None, recommended, node),
        'recommended': recommended,
    }
    if kind == 'bool':
        field['value'] = bool(node.value)
    elif kind == 'lines':
        field['lines'] = [item.value for item in node.elts if isinstance(item, ast.Constant)]
    elif kind == 'pairs':
        field['pairs'] = [_pair_display(text, item) for item in node.elts if isinstance(item, ast.Tuple)]
    elif kind == 'path':
        field['text'] = '' if evaluated is None else str(evaluated)
    elif kind == 'none':
        field['text'] = 'None'
    elif kind == 'str' and _is_derived(node):
        field['text'] = '' if evaluated is None else str(evaluated)
    elif kind == 'str':
        field['text'] = node.value
    elif kind in ('int', 'float'):
        field['text'] = slice_text(text, node)
    else:
        raise ConfigError('不能显示 %s.%s' % (class_name, name))
    return field


def _shortcut_fields(class_name, name, node):
    prefix = 'Windows' if name == 'shortcuts' else 'macOS'
    fields = []
    for index, item in enumerate(node.elts):
        if not isinstance(item, ast.Dict):
            raise ConfigError('快捷键不是字典：%s.%s' % (class_name, name))
        for key_node, value_node in zip(item.keys, item.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise ConfigError('快捷键的名字不是字符串')
            key = key_node.value
            kind = classify(value_node)
            if kind not in ('str', 'bool'):
                raise ConfigError('快捷键的 %s 不能编辑' % key)
            recommended = key in SHORTCUT_RECOMMENDED
            field = {
                'id': '%s.%s.%d.%s' % (class_name, name, index, key),
                'label': '%s %d · %s' % (prefix, index + 1, key),
                'section': '快捷键',
                'kind': kind,
                'help': _help(class_name, name, key, recommended, value_node),
                'recommended': recommended,
            }
            if kind == 'bool':
                field['value'] = bool(value_node.value)
            else:
                field['text'] = value_node.value
            fields.append(field)
    return fields


def _public(field):
    shown = {
        'id': field['id'],
        'label': field['label'],
        'kind': field['kind'],
        'help': field['help'],
        'recommended': field['recommended'],
    }
    for key in ('value', 'text', 'lines', 'pairs'):
        if key in field:
            shown[key] = field[key]
    return shown


def _recommended(class_name, name, subkey):
    if subkey:
        return subkey in SHORTCUT_RECOMMENDED
    if class_name == 'ClientConfig':
        return name in CLIENT_RECOMMENDED
    if class_name == 'ServerConfig':
        return name in SERVER_RECOMMENDED
    if class_name == 'ModelPaths':
        return True
    if class_name == 'ModelDownloadLinks':
        return True
    if class_name in CLASS_SECTION:
        return (class_name, name) not in ARGS_EDITABLE
    return False


def _section(class_name, name):
    if class_name == 'ClientConfig':
        return CLIENT_SECTION.get(name, '其它')
    if class_name == 'ServerConfig':
        return SERVER_SECTION.get(name, '其它')
    return CLASS_SECTION.get(class_name, '其它')


def _help(class_name, name, subkey, recommended, node):
    text = _help_text(class_name, name, subkey, node)
    if _is_derived(node) and '不再跟着' not in text:
        text += ' 这是从模型路径算出来的。改过之后写成固定字符串，不再跟着上面的路径变。'
    if recommended:
        text += ' 这是推荐值，要双击这一行，确认后才能改。'
    return text


def _help_text(class_name, name, subkey, node):
    if subkey == 'key' and name == 'darwin_shortcuts':
        return 'macOS 的按键名。右 Option 写 alt_r。不要改回 caps_lock，Mac 上不吞噬这个键。'
    if subkey == 'key':
        return '按键名。字母、功能键、控制键，或鼠标侧键 x1、x2。'
    if subkey == 'type':
        return 'keyboard 是键盘，mouse 是鼠标。'
    if subkey == 'suppress' and name == 'darwin_shortcuts':
        return '是否挡住这个键。macOS 的右 Option 默认不挡，别的程序还能收到它。'
    if subkey == 'suppress':
        return '是否挡住这个键。挡住后不传给别的程序；短按会再补发一次。'
    if subkey == 'hold_mode':
        return '开着是按住录音、松开停止。关掉是点一下开始，再点一下停止。'
    if subkey == 'enabled':
        return '是否启用这一条快捷键。关掉后启动时不再监听它。'
    special = _STATIC_HELP.get((class_name, name))
    if special:
        return special
    common = _NAME_HELP.get(name)
    if common:
        if class_name == 'ModelPaths' or _is_path(node):
            return common + ' 改成别的位置后会写成 Path(\'...\'），不再跟着上一级目录变。'
        if _is_derived(node):
            return common + ' 这是从模型路径算出来的。改过之后写成固定字符串，不再跟着上面的路径变。'
        return common
    if class_name == 'ModelPaths' or _is_path(node):
        return '模型或配置文件的相对路径。改成别的位置后会写成 Path(\'...\'），不再跟着上一级目录变。'
    if _is_derived(node):
        return '这是从模型路径算出来的。改过之后写成固定字符串，不再跟着上面的路径变。'
    return '%s.%s' % (class_name, name)


_NAME_HELP = {
    'addr': '要连接或绑定的地址。客户端默认 127.0.0.1，服务端默认 0.0.0.0。',
    'port': '端口。客户端和服务端要一致，默认 6016。',
    'model_dir': '模型根目录。',
    'mlx_dir': 'Apple Silicon 的 MLX 权重目录。',
    'mlx_sensevoice_dir': 'SenseVoice 的 MLX 目录。',
    'mlx_fun_asr_dir': 'Fun-ASR-Nano 的 MLX 目录。',
    'mlx_qwen_17_dir': 'Qwen3-ASR 1.7B 8bit 的 MLX 目录。',
    'mlx_qwen_06_dir': 'Qwen3-ASR 0.6B 8bit 的 MLX 目录。',
    'mlx_aligner_dir': '强制对齐器的 MLX 目录。',
    'paraformer_dir': 'Paraformer 模型目录。',
    'paraformer_model': 'Paraformer 的 onnx 文件。',
    'paraformer_tokens': 'Paraformer 的 tokens 文件。',
    'punc_model_dir': '标点模型文件。',
    'sensevoice_dir': 'SenseVoice ONNX 目录。',
    'sensevoice_encoder': 'SenseVoice 编码器。',
    'sensevoice_decoder': 'SenseVoice 解码器。',
    'sensevoice_tokenizer': 'SenseVoice 分词模型。',
    'fun_asr_nano_gguf_dir': 'Fun-ASR-Nano GGUF 目录。',
    'fun_asr_nano_gguf_encoder_adaptor': 'Fun-ASR 编码器。',
    'fun_asr_nano_gguf_ctc': 'Fun-ASR 的 CTC 文件。',
    'fun_asr_nano_gguf_llm_decode': 'Fun-ASR 的 GGUF 解码器。',
    'fun_asr_nano_gguf_token': 'Fun-ASR 的 tokens 文件。',
    'fun_asr_nano_gguf_hotwords': 'Fun-ASR 使用的服务端热词文件。',
    'qwen3_asr_gguf_dir': 'Qwen3-ASR GGUF 目录。',
    'qwen3_asr_gguf_encoder_frontend': 'Qwen3-ASR 编码器前半。',
    'qwen3_asr_gguf_encoder_backend': 'Qwen3-ASR 编码器后半。',
    'qwen3_asr_gguf_llm_decode': 'Qwen3-ASR 的 GGUF 解码器。',
    'force_aligner_gguf_dir': '强制对齐器目录。',
    'force_aligner_gguf_encoder_frontend': '对齐器编码器前半。',
    'force_aligner_gguf_encoder_backend': '对齐器编码器后半。',
    'force_aligner_gguf_llm_decode': '对齐器的 GGUF 解码器。',
}

_STATIC_HELP = {
    ('ClientConfig', 'threshold'): '按下超过这么多秒才算长按，短于它就当普通按键。单位是秒。',
    ('ClientConfig', 'paste'): 'Windows 上是否先写入剪贴板再模拟粘贴。macOS 不读这一项。',
    ('ClientConfig', 'darwin_paste'): 'macOS 上松开按键后，是否把识别结果粘贴到当前应用。',
    ('ClientConfig', 'restore_clip'): '粘贴完成之后，是否把原来的剪贴板内容放回去。',
    ('ClientConfig', 'paste_apps'): '这些程序即使没开粘贴，也强制粘贴。一行一个程序名，空行不算。增加或删除一行时，写在这个列表里面的注释不会保留。',
    ('ClientConfig', 'enter_apps'): '输出完成后自动按回车。一行是「程序名, 延迟秒数」。增加或删除一行时，写在这个列表里面的注释不会保留。',
    ('ClientConfig', 'save_audio'): '是否把每次录音存成文件。',
    ('ClientConfig', 'audio_name_len'): '用识别结果的前多少个字当作录音文件名。建议不要超过 200。',
    ('ClientConfig', 'context'): '给 Fun-ASR-Nano 的提示，例如人名、地名、专业词。',
    ('ClientConfig', 'language'): '识别语言。auto 是自动。各引擎能识别的范围不一样，也可以写 chinese、english、japanese。',
    ('ClientConfig', 'trash_punc'): '识别结果末尾要去掉的标点。',
    ('ClientConfig', 'trash_punc_thresh'): '结果短于这么多个词时，强制去掉末尾标点。',
    ('ClientConfig', 'trash_punc_apps'): '这些程序里总是去掉末尾标点。一行一个，空行不算。',
    ('ClientConfig', 'traditional_convert'): '是否把识别结果转成繁体。',
    ('ClientConfig', 'traditional_locale'): '繁体地区。zh-hant 是标准繁体，zh-tw 是台湾，zh-hk 是香港。',
    ('ClientConfig', 'hot'): '是否按音素匹配热词并替换。',
    ('ClientConfig', 'hot_thresh'): '相似度达到这个值才真正替换热词。越高越严格。',
    ('ClientConfig', 'hot_similar'): '相似度达到这个值就放进 LLM 的上下文，不一定替换上屏。',
    ('ClientConfig', 'hot_rule'): '是否启用 hot-rule.txt 里的正则或等号替换。',
    ('ClientConfig', 'llm_enabled'): '是否启用 LLM 润色。需要 LLM 目录里的角色文件。',
    ('ClientConfig', 'llm_stop_key'): '打断 LLM 继续输出的按键。',
    ('ClientConfig', 'enable_tray'): '是否显示菜单栏图标。',
    ('ClientConfig', 'log_level'): '日志详细程度。DEBUG 最详细，然后是 INFO、WARNING、ERROR、CRITICAL。',
    ('ClientConfig', 'mic_seg_duration'): '麦克风听写时每段多长。单位是这段音频里的秒，不是系统时间。',
    ('ClientConfig', 'mic_seg_overlap'): '麦克风相邻两段重叠多少秒音频，不是系统时间。',
    ('ClientConfig', 'file_seg_duration'): '转录文件时每段多长。单位是音频文件里的秒，不是系统时间。',
    ('ClientConfig', 'file_seg_overlap'): '文件相邻两段重叠多少秒音频，不是系统时间。',
    ('ClientConfig', 'file_save_srt'): '转录文件时是否在旁边写 srt 字幕。',
    ('ClientConfig', 'file_save_txt'): '转录文件时是否写按标点切开的 txt。',
    ('ClientConfig', 'file_save_json'): '转录文件时是否写带时间戳的 json。',
    ('ClientConfig', 'file_save_merge'): '是否再写一份没有切开的 merge.txt。默认不写。',
    ('ClientConfig', 'udp_broadcast'): '是否把识别结果用 UDP 广播出去。默认关。',
    ('ClientConfig', 'udp_broadcast_targets'): '广播到哪些地址。一行是「地址, 端口」。增加或删除一行时，写在这个列表里面的注释不会保留。',
    ('ClientConfig', 'udp_control'): '是否听 UDP 的 START/STOP 来控制录音。默认关。',
    ('ClientConfig', 'udp_control_addr'): 'UDP 控制听在哪个地址。0.0.0.0 表示别的机器也能发命令。',
    ('ClientConfig', 'udp_control_port'): 'UDP 控制的端口。',
    ('ServerConfig', 'addr'): '服务端绑定的地址。0.0.0.0 表示本机所有网卡都能连。',
    ('ServerConfig', 'port'): '服务端监听端口。客户端要填同一个端口。',
    ('ServerConfig', 'model_type'): '用哪个语音模型。可以是 sensevoice、fun_asr_nano、qwen_asr、paraformer。',
    ('ServerConfig', 'model_backend'): 'auto 在 Mac 上走 MLX。onnx 强制现有引擎。mlx 强制 MLX，Paraformer 除外。',
    ('ServerConfig', 'qwen_mlx_variant'): 'auto 按内存选 1.7B 8bit 或 0.6B 8bit。也可以写成 0.6b、1.7b，或 1.7b-4bit、1.7b-6bit、1.7b-mxfp4、0.6b-4bit、0.6b-6bit、0.6b-mxfp4。',
    ('ServerConfig', 'mlx_auto_download'): '缺模型目录时是否下载。默认只报缺哪个目录，不下载。',
    ('ServerConfig', 'format_num'): '输出时是否把中文数字转成阿拉伯数字。',
    ('ServerConfig', 'format_spell'): '输出时是否调整中文和英文之间的空格。',
    ('ServerConfig', 'enable_tray'): '服务端是否显示菜单栏图标。',
    ('ServerConfig', 'hotwords_path'): '服务端全局热词文件。改成别的位置后会写成 Path(\'...\'），不再跟着程序目录变。',
    ('ServerConfig', 'log_level'): '服务端日志详细程度。DEBUG 最详细，然后是 INFO、WARNING、ERROR、CRITICAL。',
    ('ServerConfig', 'aligner_idle_timeout'): '对齐引擎空闲多少秒后释放显存。0 表示不释放。',
    ('ServerConfig', 'gpu_boost_enabled'): '有识别任务时是否先拉高显存频率。需要管理员权限，默认关。',
    ('ServerConfig', 'gpu_boost_cmd'): '拉高显存频率的命令。按实际显卡改。',
    ('ServerConfig', 'gpu_unboost_cmd'): '恢复默认显存频率的命令。',
    ('ServerConfig', 'gpu_unboost_timeout'): '空闲多少秒后取消显存加速。',
    ('ModelDownloadLinks', 'models_page'): '模型下载页面。只是说明用，不参与这一次识别。',
    ('ParaformerArgs', 'paraformer'): 'Paraformer 模型文件。',
    ('ParaformerArgs', 'tokens'): 'Paraformer 的 tokens 文件。',
    ('ParaformerArgs', 'num_threads'): 'Paraformer 使用的线程数。',
    ('ParaformerArgs', 'sample_rate'): '音频采样率。这段配置按 16000 Hz 来。',
    ('ParaformerArgs', 'feature_dim'): '特征维度。',
    ('ParaformerArgs', 'decoding_method'): '解码方式。默认 greedy_search。',
    ('ParaformerArgs', 'provider'): '推理后端。这里默认 cpu。',
    ('ParaformerArgs', 'debug'): '是否打印 Paraformer 的调试信息。',
    ('SenseVoiceArgs', 'encoder_path'): 'SenseVoice 编码器路径。',
    ('SenseVoiceArgs', 'decoder_path'): 'SenseVoice 解码器路径。',
    ('SenseVoiceArgs', 'tokenizer_path'): 'SenseVoice 分词模型路径。',
    ('SenseVoiceArgs', 'itn'): '是否让 SenseVoice 直接输出阿拉伯数字。',
    ('SenseVoiceArgs', 'onnx_provider'): 'ONNX 推理后端，例如 CPU 或 DML。界面填文件里现在的值。',
    ('SenseVoiceArgs', 'top_k'): '热词检索使用的 CTC 空间大小。',
    ('SenseVoiceArgs', 'dml_pad_to'): '打开 DirectML 时，短音频填充到多少秒。',
    ('FunASRNanoGGUFArgs', 'encoder_onnx_path'): 'Fun-ASR 编码器路径。',
    ('FunASRNanoGGUFArgs', 'ctc_onnx_path'): 'Fun-ASR CTC 路径。',
    ('FunASRNanoGGUFArgs', 'decoder_gguf_path'): 'Fun-ASR GGUF 解码器路径。',
    ('FunASRNanoGGUFArgs', 'tokens_path'): 'Fun-ASR tokens 路径。',
    ('FunASRNanoGGUFArgs', 'onnx_provider'): 'ONNX 推理后端，例如 CPU 或 DML。',
    ('FunASRNanoGGUFArgs', 'llm_use_gpu'): '是否用 GPU 跑 Fun-ASR 的 GGUF。',
    ('FunASRNanoGGUFArgs', 'vulkan_force_fp32'): 'GPU 精度溢出时，是否强制用 FP32。',
    ('FunASRNanoGGUFArgs', 'enable_ctc'): '是否启用 CTC 热词检索。',
    ('FunASRNanoGGUFArgs', 'n_predict'): 'LLM 最多生成多少个 token。',
    ('FunASRNanoGGUFArgs', 'n_threads'): '线程数。None 表示自动。',
    ('FunASRNanoGGUFArgs', 'similar_threshold'): '热词相似度超过这个值才放进解码器上下文。',
    ('FunASRNanoGGUFArgs', 'max_hotwords'): '放进上下文的热词数量上限。',
    ('FunASRNanoGGUFArgs', 'dml_pad_to'): '打开 DirectML 时，短音频填充到多少秒。',
    ('FunASRNanoGGUFArgs', 'verbose'): '是否打印 Fun-ASR 的详细日志。',
    ('Qwen3ASRGGUFArgs', 'model_dir'): 'Qwen3-ASR 模型目录。',
    ('Qwen3ASRGGUFArgs', 'encoder_frontend_fn'): 'Qwen3-ASR 编码器前半的文件名。',
    ('Qwen3ASRGGUFArgs', 'encoder_backend_fn'): 'Qwen3-ASR 编码器后半的文件名。',
    ('Qwen3ASRGGUFArgs', 'llm_fn'): 'Qwen3-ASR 解码器文件名。',
    ('Qwen3ASRGGUFArgs', 'onnx_provider'): 'ONNX 推理后端，例如 CPU 或 DML。',
    ('Qwen3ASRGGUFArgs', 'llm_use_gpu'): '是否用 GPU 跑 Qwen3-ASR 的 GGUF。',
    ('Qwen3ASRGGUFArgs', 'n_ctx'): '上下文窗口有多少 token。',
    ('Qwen3ASRGGUFArgs', 'chunk_size'): '分段长度，单位是音频里的秒。',
    ('Qwen3ASRGGUFArgs', 'memory_num'): '保留多少段记忆。',
    ('Qwen3ASRGGUFArgs', 'dml_pad_to'): '打开 DirectML 时，短音频填充到多少秒。',
    ('Qwen3ASRGGUFArgs', 'verbose'): '是否打印 Qwen3-ASR 的详细日志。',
    ('ForceAlignerGGUFArgs', 'model_dir'): '对齐器模型目录。',
    ('ForceAlignerGGUFArgs', 'encoder_frontend_fn'): '对齐器编码器前半的文件名。',
    ('ForceAlignerGGUFArgs', 'encoder_backend_fn'): '对齐器编码器后半的文件名。',
    ('ForceAlignerGGUFArgs', 'llm_fn'): '对齐器解码器文件名。',
    ('ForceAlignerGGUFArgs', 'onnx_provider'): 'ONNX 推理后端。注释里写了推荐 DML，文件里现在是什么，界面就填什么。',
    ('ForceAlignerGGUFArgs', 'llm_use_gpu'): '是否用 GPU 跑对齐器的 GGUF。',
    ('ForceAlignerGGUFArgs', 'n_ctx'): '对齐器的上下文窗口有多少 token。',
    ('ForceAlignerGGUFArgs', 'dml_pad_to'): '打开 DirectML 时，短音频填充到多少秒。',
}


def _pair_display(text, node):
    left = node.elts[0]
    right = node.elts[1]
    left_text = left.value if isinstance(left, ast.Constant) else slice_text(text, left)
    return [str(left_text), slice_text(text, right)]


def _shortcut_label(fields, prefix):
    chosen = []
    enabled = {}
    keys = {}
    for field in fields:
        if not field['id'].startswith(prefix + '.'):
            continue
        parts = field['id'].split('.')
        index = parts[2]
        if field['id'].endswith('.enabled'):
            enabled[index] = field.get('value', True)
        if field['id'].endswith('.key'):
            keys[index] = field.get('text', '')
    for index in sorted(keys, key=int):
        if enabled.get(index, True):
            chosen.append(_format_key(keys[index]))
    return '、'.join(chosen) if chosen else '未配置快捷键'


def _format_key(key):
    if key in KEY_LABELS:
        return KEY_LABELS[key]
    return key.replace('_', ' ').title()


def _index(fields):
    return {field['id']: field for field in fields}


def _on_off(value):
    return '开' if value else '关'


def _is_path(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path':
        return True
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)


def _is_derived(node):
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr in ('as_posix', 'name')


def _try_eval(node, class_env, env):
    try:
        return _eval(node, class_env, env)
    except ConfigError:
        return None


def _eval(node, class_env, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in class_env:
            raise ConfigError('还没有 %s' % node.id)
        return class_env[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path':
        if not node.args:
            return ''
        return str(_eval(node.args[0], class_env, env))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _join(_eval(node.left, class_env, env), _eval(node.right, class_env, env))
    if isinstance(node, ast.Call) and _is_derived(node):
        return _eval_attr(node.func, class_env, env)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr not in ('as_posix', 'name'):
        key = '%s.%s' % (node.value.id, node.attr)
        if key not in env:
            raise ConfigError('还没有 %s' % key)
        return env[key]
    if isinstance(node, ast.Attribute) and node.attr in ('as_posix', 'name'):
        return _eval_attr(node, class_env, env)
    raise ConfigError('不能计算路径')


def _eval_attr(node, class_env, env):
    if node.attr == 'as_posix':
        return str(_eval(node.value, class_env, env)).replace('\\', '/')
    if node.attr == 'name':
        text = str(_eval(node.value, class_env, env)).rstrip('/')
        return text.split('/')[-1] if text else ''
    raise ConfigError('不能计算路径')


def _join(left, right):
    left_text = '' if left is None else str(left)
    right_text = '' if right is None else str(right)
    if left_text in ('', '.'):
        return right_text
    return left_text.rstrip('/') + '/' + right_text.lstrip('/')


def _assignment_name(node):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return node.target.id
    return None


def _find_node(tree, field_id):
    parts = field_id.split('.')
    if len(parts) < 2:
        return None
    class_name, attr = parts[0], parts[1]
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if _assignment_name(item) != attr:
                continue
            current = item.value
            for part in parts[2:]:
                if part.isdigit():
                    if not isinstance(current, (ast.List, ast.Tuple)) or int(part) >= len(current.elts):
                        return None
                    current = current.elts[int(part)]
                    continue
                if not isinstance(current, ast.Dict):
                    return None
                found = None
                for key_node, value_node in zip(current.keys, current.values):
                    if isinstance(key_node, ast.Constant) and key_node.value == part:
                        found = value_node
                        break
                if found is None:
                    return None
                current = found
            return current
    return None


def read_version(text):
    tree = ast.parse(text)
    for node in tree.body:
        if _assignment_name(node) == '__version__' and isinstance(node.value, ast.Constant):
            return str(node.value.value)
    return ''


def line_offsets(text):
    offsets = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        offsets.append(cursor)
        cursor += len(line.encode('utf-8'))
    if not offsets:
        offsets.append(0)
    return offsets


def span(text, node):
    offsets = line_offsets(text)
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return start, end


def slice_text(text, node):
    raw = text.encode('utf-8')
    start, end = span(text, node)
    return raw[start:end].decode('utf-8')


def replace_span(text, node, replacement):
    return replace_many(text, [(node, replacement)])


def replace_many(text, pairs):
    """从后往前替换，前面的位置不会被后面的长度变化挤开。"""
    raw = bytearray(text.encode('utf-8'))
    located = []
    for node, replacement in pairs:
        start, end = span(text, node)
        located.append((start, end, replacement.encode('utf-8')))
    for start, end, blob in sorted(located, key=lambda item: item[0], reverse=True):
        raw[start:end] = blob
    return raw.decode('utf-8')


def _write_updates(path, updates):
    if not updates:
        return
    text = path.read_text(encoding='utf-8')
    updated = apply_text(text, updates)
    if updated == text:
        return
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(updated, encoding='utf-8')
    temporary.replace(path)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ('dump', 'apply'):
        print('用法：python -m core.tools.config_form dump|apply [--root 目录]', file=sys.stderr)
        return 2
    command = argv[0]
    root = Path('.')
    if '--root' in argv:
        index = argv.index('--root')
        root = Path(argv[index + 1])
    try:
        if command == 'dump':
            json.dump(load_form(root), sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write('\n')
            return 0
        payload = json.load(sys.stdin)
        count = apply_files(root, payload.get('updates', []))
        json.dump({'ok': True, 'count': count}, sys.stdout, ensure_ascii=False)
        sys.stdout.write('\n')
        return 0
    except (ConfigError, OSError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())


if __name__ == '__main__':
    raise SystemExit(main())
