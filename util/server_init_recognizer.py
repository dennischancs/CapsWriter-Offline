import time
import sherpa_onnx
from multiprocessing import Queue
import signal
import threading # 新增
from platform import system
from config import ServerConfig as Config
from config import ParaformerArgs, ModelPaths
from util.server_cosmic import console
from util.server_recognize import recognize
from util.empty_working_set import empty_current_working_set

# 使用全局变量在进程内共享标点模型和加载状态
global_punc_model = None
punc_model_loaded = threading.Event()



def disable_jieba_debug():
    # 关闭 jieba 的 debug
    import jieba
    import logging
    jieba.setLogLevel(logging.INFO)

def load_punc_model_in_background():
    """在后台线程中加载标点模型"""
    global global_punc_model
    console.print('[yellow]后台加载标点模型中...[/yellow]')
    try:
        # 将导入移到函数内部，避免在主线程中加载
        from funasr_onnx import CT_Transformer
        global_punc_model = CT_Transformer(ModelPaths.punc_model_dir, quantize=True)
        console.print(f'[green4]后台标点模型载入完成[/green4]')
    except Exception as e:
        console.print(f'[bold red]后台标点模型加载失败: {e}[/bold red]')
        # 即使加载失败，也设置事件，以免主循环一直等待
    finally:
        punc_model_loaded.set() # 设置事件，表示加载尝试已完成（无论成功与否）


def init_recognizer(queue_in: Queue, queue_out: Queue, sockets_id):
    global global_punc_model # 声明使用全局变量

    # Ctrl-C 退出
    signal.signal(signal.SIGINT, lambda signum, frame: exit())

    # 导入核心模块
    with console.status("载入核心模块中…", spinner="bouncingBall", spinner_style="yellow"):
        import sherpa_onnx
        # funasr_onnx 的导入移到后台加载函数中
        disable_jieba_debug()
    console.print('[green4]核心模块加载完成', end='\n\n')

    # 载入语音模型
    console.print('[yellow]语音模型载入中', end='\r'); t1 = time.time()
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        **{key: value for key, value in ParaformerArgs.__dict__.items() if not key.startswith('_')}
    )
    console.print(f'[green4]语音模型载入完成', end='\n\n')

    # 启动后台线程加载标点模型
    if Config.format_punc:
        punc_loader_thread = threading.Thread(target=load_punc_model_in_background, daemon=True)
        punc_loader_thread.start()
        console.print('[cyan]标点模型已在后台开始加载，服务器可以开始接收任务。[/cyan]', end='\n\n')
    else:
        # 如果配置中不启用标点，则直接标记为已加载
        punc_model_loaded.set()

    console.print(f'语音模型加载耗时 {time.time() - t1 :.2f}s', end='\n\n')

    # 清空物理内存工作集
    if system() == 'Windows':
        empty_current_working_set()

    queue_out.put(True)  # 通知主进程，核心服务已就绪

    while True:
        # 从队列中获取任务消息
        # 阻塞最多1秒，便于中断退出
        try:
            task = queue_in.get(timeout=1)       
        except:
            continue

        if task.socket_id not in sockets_id:    # 检查任务所属的连接是否存活
            continue

        # 在执行识别前，获取当前可用的 punc_model
        current_punc_model = global_punc_model if punc_model_loaded.is_set() else None
        
        result = recognize(recognizer, current_punc_model, task)   # 执行识别
        queue_out.put(result)      # 返回结果
