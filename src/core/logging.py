import structlog
from structlog.processors import CallsiteParameter, CallsiteParameterAdder
from structlog.stdlib import LoggerFactory
import logging
import sys
from .config import settings


def setup_logging():
    """配置结构化日志"""
    
    # 设置日志级别
    log_level = getattr(logging, settings.LOG_LEVEL.upper())
    
    # 配置标准库日志
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # 配置structlog
    structlog.configure(
        processors=[
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
            # 开发环境使用漂亮的控制台输出
            structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """获取logger实例"""
    return structlog.get_logger(name)


# 初始化日志系统
setup_logging()
