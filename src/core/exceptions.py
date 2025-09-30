"""
FAA 统一异常处理体系

设计原则：
1. 分层异常：基础异常 → 模块异常 → 具体异常
2. 包含上下文信息：trace_id、user_id、error_code 等
3. 支持国际化错误消息
4. 便于监控和告警
"""
from typing import Optional, Dict, Any
import uuid


class FAError(Exception):
    """FAA 基础异常类
    
    所有 FAA 异常的基类，包含通用的错误信息和上下文
    """
    
    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        trace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.trace_id = trace_id
        self.user_id = user_id
        self.context = context or {}
        self.cause = cause
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于日志记录和 API 响应"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "context": self.context,
            "cause": str(self.cause) if self.cause else None
        }
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.trace_id:
            parts.append(f"trace_id={self.trace_id}")
        if self.error_code:
            parts.append(f"code={self.error_code}")
        return f"{self.__class__.__name__}: {' | '.join(parts)}"


class AIEngineError(FAError):
    """AI 引擎相关异常"""
    pass


class AnalysisError(AIEngineError):
    """消息分析异常 - AI 理解失败"""
    pass


class ContextResolutionError(AIEngineError):
    """上下文解析异常 - 无法获取需要的上下文数据"""
    pass


class ToolPlanningError(AIEngineError):
    """工具规划异常 - 无法制定执行计划"""
    pass


class MCPToolError(FAError):
    """MCP 工具调用异常"""
    pass


class ToolNotFoundError(MCPToolError):
    """工具不存在异常"""
    pass


class ToolTimeoutError(MCPToolError):
    """工具调用超时异常"""
    pass


class ToolExecutionError(MCPToolError):
    """工具执行失败异常"""
    pass


class PromptError(FAError):
    """Prompt 处理异常"""
    pass


class PromptVersionError(PromptError):
    """Prompt 版本错误"""
    pass


class PromptRenderError(PromptError):
    """Prompt 渲染错误"""
    pass


class LLMError(FAError):
    """LLM 调用异常"""
    pass


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""
    pass


class LLMRateLimitError(LLMError):
    """LLM 调用频率限制"""
    pass


class LLMQuotaExceededError(LLMError):
    """LLM 配额超限"""
    pass


class ConfigurationError(FAError):
    """配置错误"""
    pass


class ValidationError(FAError):
    """数据验证错误"""
    pass


# 错误代码映射（便于前端处理和用户提示）
ERROR_MESSAGES = {
    # AI 引擎错误
    "AnalysisError": "消息理解失败，请尝试重新表达",
    "ContextResolutionError": "无法获取相关上下文信息",
    "ToolPlanningError": "无法制定执行计划",
    
    # MCP 工具错误
    "ToolNotFoundError": "请求的功能暂时不可用",
    "ToolTimeoutError": "操作超时，请稍后重试",
    "ToolExecutionError": "操作执行失败",
    
    # LLM 错误
    "LLMTimeoutError": "AI 响应超时，请重试",
    "LLMRateLimitError": "请求过于频繁，请稍后重试",
    "LLMQuotaExceededError": "今日 AI 服务额度已用完",
    
    # 通用错误
    "ConfigurationError": "系统配置错误",
    "ValidationError": "输入数据格式错误",
}


def get_user_friendly_message(error: FAError) -> str:
    """获取用户友好的错误消息
    
    Args:
        error: FAA 异常实例
        
    Returns:
        用户友好的错误描述
    """
    error_type = error.__class__.__name__
    friendly_msg = ERROR_MESSAGES.get(error_type, "系统暂时出现问题，请稍后重试")
    
    # 特殊情况的个性化处理
    if isinstance(error, ToolTimeoutError) and error.context.get('tool_name'):
        tool_name = error.context['tool_name']
        return f"{friendly_msg}（{tool_name} 功能响应超时）"
    
    return friendly_msg


def create_error_context(
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """创建错误上下文信息
    
    便于在异常处理中快速构建上下文
    """
    context = {
        "trace_id": trace_id,
        "user_id": user_id,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    context.update(kwargs)
    return context
