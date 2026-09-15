# -*- coding: utf-8 -*-
"""
书斋 V66 — 统一日志配置

提供：
- setup_logging()      — 初始化控制台+文件双输出（TimedRotatingFileHandler，按天轮转保留7天）
- log_exceptions()     — 装饰器：自动捕获异常 → logger.error(堆栈) → re-raise

用法：
    # server.py 启动时调用一次
    from backend.logger_config import setup_logging
    setup_logging(log_dir=None)

    # 业务模块仍可用标准 getLogger
    import logging
    logger = logging.getLogger(__name__)
"""
import functools
import logging
import os
import traceback
from logging.handlers import TimedRotatingFileHandler

_INITIALIZED = False


def setup_logging(app_name: str = "shuzhai", log_dir: str = None):
    """
    初始化全局日志配置。调用一次后再次调用为幂等操作。

    Args:
        app_name: 日志文件名前缀
        log_dir: 日志目录，None 则默认为项目根目录下的 logs/
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    # 解析 log_dir 默认值
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 统一格式
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # — 控制台 handler：WARNING+ → stderr —
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    # — 文件 handler（shuzhai.log）：WARNING+，按天轮转，保留 7 天 —
    warning_file = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{app_name}.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    warning_file.setLevel(logging.WARNING)
    warning_file.setFormatter(fmt)
    root.addHandler(warning_file)

    # — 错误专用文件（error.log）：ERROR+，按天轮转，保留 7 天 —
    error_file = TimedRotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(fmt)
    root.addHandler(error_file)

    # — 抑制第三方库噪音 —
    for noisy in ("httpx", "urllib3", "faiss", "sentence_transformers", "chromadb",
                  "openai", "httpcore", "PIL", "matplotlib", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _INITIALIZED = True
    logger = logging.getLogger(__name__)
    logger.info("日志系统初始化完成，日志目录: %s", log_dir)


def log_exceptions(logger: logging.Logger = None, reraise: bool = True):
    """
    自动记录异常堆栈的装饰器。

    Args:
        logger: 目标 Logger（None 则按被装饰函数的 __module__ 自动获取）
        reraise: True=记录后重新抛出（默认）; False=吞掉异常返回 None

    用法:
        @log_exceptions()
        def risky_handler():
            ...

        @log_exceptions(reraise=False)
        def optional_cleanup():
            ...  # 失败只记日志不阻断
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                _logger = logger or logging.getLogger(func.__module__)
                _logger.error(
                    "[%s.%s] 未捕获异常:\n%s",
                    func.__module__,
                    func.__qualname__,
                    traceback.format_exc().strip(),
                )
                if reraise:
                    raise
                return None

        return wrapper

    return decorator
