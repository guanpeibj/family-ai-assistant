import structlog
from structlog.processors import CallsiteParameter, CallsiteParameterAdder
from structlog.stdlib import LoggerFactory
import logging
import logging.handlers
import sys
from pathlib import Path
from .config import settings


def setup_logging():
    """配置结构化日志"""
    
    # 设置日志级别
    log_level = getattr(logging, settings.LOG_LEVEL.upper())
    
    # 创建日志目录
    log_dir = Path(settings.LOG_DIR) if hasattr(settings, 'LOG_DIR') else Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 清理现有handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # 标准输出 handler（总是需要，Docker 会捕获）
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    root_logger.addHandler(stdout_handler)
    
    # 文件 handlers（开发环境可选，生产环境由 Docker 日志管理）
    # 仅在明确配置 LOG_DIR 时才写入文件
    if hasattr(settings, 'LOG_DIR') and settings.LOG_DIR:
        # 主日志文件
        app_handler = logging.handlers.RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        app_handler.setLevel(log_level)
        root_logger.addHandler(app_handler)
        
        # 错误日志文件
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)
    
    root_logger.setLevel(log_level)
    
    # 配置structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.FILENAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.FUNC_NAME,
            ]
        ),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # 根据环境选择渲染器
    if settings.DEBUG:
        # 开发环境：彩色控制台
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # 生产环境：JSON（便于日志分析）
        renderer = structlog.processors.JSONRenderer()
    
    shared_processors.append(renderer)
    
    # 配置structlog
    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """获取logger实例"""
    return structlog.get_logger(name)


# 初始化日志系统
setup_logging()
