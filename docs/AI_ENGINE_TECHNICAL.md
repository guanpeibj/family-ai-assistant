# AI引擎技术文档 (ai_engine.py)

## 文档信息
- **文件路径**: `src/ai_engine.py`
- **代码行数**: ~2000行
- **最后更新**: 2025.09.29
- **版本**: V2 Enhanced

## 一、文件结构概览

```python
# 1. 导入和配置 (行 1-40)
import json, asyncio, uuid, time...
from pydantic import BaseModel
import structlog

# 2. 异常定义 (行 41-70)
class BaseAIException(Exception)
class AnalysisError, ContextResolutionError...

# 3. 数据模型 (行 71-130)
class UnderstandingModel(BaseModel)  # AI理解结果
class ContextRequestModel(BaseModel) # 上下文请求
class ToolPlanModel(BaseModel)       # 工具计划
class AnalysisModel(BaseModel)       # 完整分析结果

# 4. 辅助类 (行 131-560)
class MessageProcessor        # 消息预处理
class ContextManager          # 上下文管理 
class CapabilityAnalyzer     # 能力分析
class ToolExecutor           # 工具执行

# 5. 主引擎类 (行 561-1990)
class AIEngineV2:
    # 初始化和配置
    # 主流程方法
    # 辅助方法
    # 缓存管理
    # 持久化
```

## 二、核心类详解

### 2.1 数据模型

#### UnderstandingModel (行 71-89)
```python
class UnderstandingModel(BaseModel):
    """AI理解结果模型 - 核心契约结构"""
    intent: Optional[str] = None                    # 用户意图
    entities: Dict[str, Any] = Field(default_factory=dict)  # 提取的实体
    need_action: bool = False                       # 是否需要执行操作
    need_clarification: bool = False                # 是否需要澄清
    missing_fields: List[str] = Field(default_factory=list)  # 缺失字段
    clarification_questions: List[str]              # 澄清问题
    suggested_reply: Optional[str] = None           # 建议回复
    context_link: Optional[Dict[str, Any]] = None   # 上下文关联
    occurred_at: Optional[str] = None               # 事件时间
    update_existing: Optional[bool] = None          # 是否更新
    original_content: Optional[str] = None          # 原始内容(调试用)
    # 思考循环字段
    thinking_depth: int = 0                         # 思考深度(0-3)
    needs_deeper_analysis: bool = False             # 需要深入分析
    analysis_reasoning: Optional[str] = None        # 分析推理
    next_exploration_areas: List[str]               # 探索方向
    metadata: Dict[str, Any]                        # 元数据
```

#### AnalysisModel (行 90-96)
```python
class AnalysisModel(BaseModel):
    """完整分析结果 - 统一契约"""
    understanding: UnderstandingModel                # 理解结果
    context_requests: List[ContextRequestModel]      # 上下文请求
    tool_plan: ToolPlanModel                        # 工具计划
    response_directives: Dict[str, Any]             # 响应指令
```

### 2.2 ContextManager (行 134-340)

#### 核心方法
```python
async def get_basic_context(user_id, thread_id, shared_thread, channel):
    """获取基础上下文"""
    # 1. 获取最近对话记录 (4条)
    # 2. 获取家庭结构信息
    # 日志: context.basic.complete
    return {'light_context': [...], 'household': {...}}

async def resolve_context_requests(context_requests, understanding, ...):
    """解析并获取额外上下文"""
    # 支持: recent_memories, semantic_search, direct_search
    # 日志: context.requests.resolved
    return resolved_context
```

#### 日志输出
- `context.basic.fetching_memories` - 开始获取记忆
- `context.memories.fetched` - 记忆获取完成(含预览)
- `context.household.fetched` - 家庭信息获取完成
- `context.requests.resolved` - 上下文请求解析完成

### 2.3 ToolExecutor (行 450-560)

#### 核心方法
```python
async def execute_plan(tool_plan, context, trace_id, user_id):
    """执行工具计划"""
    # 1. 获取工具元数据和时间预算
    # 2. 执行工具步骤 
    # 3. 支持验证循环(最多3轮)
    return execution_result

async def _execute_tool_step(step, context, trace_id, user_id):
    """执行单个工具步骤"""
    # 1. 准备参数
    # 2. 调用MCP工具
    # 3. 处理结果
    return result
```

## 三、主引擎类 AIEngineV2

### 3.1 初始化 (行 567-589)
```python
def __init__(self):
    # 核心组件
    self.llm = LLMClient()                    # LLM客户端
    self.mcp_client = None                    # MCP客户端
    self.mcp_url = 'http://faa-mcp:8000'     # MCP地址
    
    # 辅助组件
    self.message_processor = MessageProcessor()
    self.context_manager = ContextManager(self)
    self.tool_executor = ToolExecutor(self)
    
    # 缓存
    self._emb_cache_by_trace = {}             # trace级缓存
    self._emb_cache_global = {}               # 全局LRU缓存
    self._tool_calls_by_trace = {}            # 工具调用记录
```

### 3.2 主流程 process_message (行 592-677)

```python
async def process_message(content: str, user_id: str, context: Dict) -> str:
    """主入口 - 6步骤流程"""
    trace_id = str(uuid.uuid4())
    start_time = asyncio.get_event_loop().time()
    
    try:
        # 步骤1: 初始化追踪 (行 685-697)
        self._init_trace(trace_id, user_id, context)
        
        # 步骤2: 消息预处理 (行 699-710)
        processed_content = await self._preprocess_message(content, context)
        logger.info("step1.preprocess.completed", duration_ms=...)
        
        # 步骤3: 获取实验版本 (行 712-725)
        prompt_version = self._get_experiment_version(user_id, context)
        
        # 步骤4: AI分析 (行 727-850)
        analysis = await self._analyze_message(...)
        logger.info("step3.analysis.completed", ...)
        
        # 步骤5: 澄清处理 (行 856-894)
        if analysis.understanding.need_clarification:
            return await self._handle_clarification(...)
        
        # 步骤6: 执行和响应 (行 895-1100)
        response = await self._execute_and_respond(...)
        logger.info("step5.execution.completed", ...)
        
        # 步骤7: 实验记录 (行 1320-1340)
        self._record_experiment_result(...)
        
        return response
        
    except Exception as e:
        return await self._handle_error(e, trace_id, user_id)
    finally:
        self._cleanup_trace(trace_id)
```

### 3.3 AI分析方法 _analyze_message (行 721-1050)

```python
async def _analyze_message(...) -> AnalysisModel:
    """支持多轮思考的AI分析"""
    
    # 思考循环 (最多3轮)
    for thinking_rounds in range(1, 4):
        
        # 第1轮: 获取基础上下文
        if thinking_rounds == 1:
            base_context = await self.context_manager.get_basic_context(...)
            logger.info("analysis.basic_context.details", ...)
        
        # 构建分析载荷
        analysis_payload = {
            "message": content,
            "user": {...},
            "context": {...}
        }
        logger.info("analysis.payload.summary", ...)
        
        # 调用LLM
        llm_start = asyncio.get_event_loop().time()
        raw_response = await self.llm.chat_json(...)
        logger.info("llm.response.summary", duration_ms=...)
        
        # 解析响应
        analysis = AnalysisModel(**raw_response)
        analysis.understanding.original_content = content
        
        # 检查是否需要深入分析
        if not needs_deeper_analysis or thinking_rounds >= 3:
            break
            
        # 获取额外上下文继续分析
        if analysis.context_requests:
            resolved_context = await self.context_manager.resolve_context_requests(...)
            accumulated_context.update(resolved_context)
    
    return analysis
```

### 3.4 工具执行 _execute_and_respond (行 895-1100)

```python
async def _execute_and_respond(...) -> str:
    """执行工具并生成响应"""
    
    # 1. 执行工具计划
    if analysis.tool_plan.steps:
        execution_result = await self.tool_executor.execute_plan(...)
        logger.info("tool_execution.verified_complete", ...)
    
    # 2. 生成响应
    response = await self._generate_response(...)
    
    # 3. 持久化对话
    await self._store_conversation(...)
    
    return response
```

## 四、关键日志点

### 4.1 主流程日志
| 日志名称 | 位置 | 含义 |
|---------|------|------|
| message.received | _init_trace | 消息接收 |
| step1.preprocess.completed | process_message | 预处理完成 |
| step2.experiment.version | process_message | 实验版本 |
| step3.analysis.completed | process_message | 分析完成 |
| step4.clarification.returned | process_message | 澄清返回 |
| step5.execution.completed | process_message | 执行完成 |

### 4.2 分析详细日志
| 日志名称 | 位置 | 含义 |
|---------|------|------|
| analysis.round.started | _analyze_message | 分析轮次开始 |
| analysis.basic_context.details | _analyze_message | 基础上下文详情 |
| analysis.payload.summary | _analyze_message | 分析载荷摘要 |
| llm.request.details | _analyze_message | LLM请求详情 |
| llm.response.summary | _analyze_message | LLM响应摘要 |
| llm.understanding.details | _analyze_message | 理解详情 |
| llm.tool_plan.details | _analyze_message | 工具计划 |
| thinking_loop.completed | _analyze_message | 思考循环完成 |

### 4.3 上下文日志
| 日志名称 | 位置 | 含义 |
|---------|------|------|
| context.basic.fetching_memories | get_basic_context | 获取记忆 |
| context.memories.fetched | get_basic_context | 记忆详情 |
| context.household.fetched | get_basic_context | 家庭信息 |
| context.requests.resolving | resolve_context_requests | 解析请求 |
| context.semantic_search.complete | resolve_context_requests | 语义搜索完成 |

## 五、性能优化点

### 5.1 缓存机制

#### 向量嵌入缓存 (行 1473-1530)
```python
async def _get_embedding_cached(text: str, trace_id: str):
    # 1. 检查trace级缓存
    # 2. 检查全局LRU缓存
    # 3. 生成新向量并缓存
    return embedding
```

#### 缓存配置
- Trace缓存: 单次请求内复用
- 全局缓存: 最多1000项, TTL=3600秒
- LRU淘汰: 容量满时移除最旧项

### 5.2 性能监控

#### 关键指标
```python
{
    "thinking_rounds": 1-2,        # 思考轮数
    "duration_ms": {
        "preprocess": <100,        # 预处理
        "analysis": <10000,        # AI分析
        "execution": <5000,        # 工具执行
        "total": <15000           # 总耗时
    },
    "tool_calls_count": 1-3,      # 工具调用数
    "cache_hit_rate": >0.5         # 缓存命中率
}
```

## 六、错误处理

### 6.1 异常体系 (行 41-70)
```python
BaseAIException
├── AnalysisError          # AI分析失败
├── ContextResolutionError # 上下文获取失败
├── ToolPlanningError      # 工具规划失败
├── MCPToolError          # MCP调用失败
├── ToolTimeoutError      # 工具超时
├── ToolExecutionError     # 工具执行失败
└── LLMError              # LLM调用失败
```

### 6.2 错误处理策略 (行 1341-1360)
```python
async def _handle_error(error, trace_id, user_id):
    # 1. 记录详细错误日志
    logger.error("message.process.error", ...)
    
    # 2. 根据错误类型返回友好消息
    if isinstance(error, AnalysisError):
        return "理解您的消息时遇到问题..."
    elif isinstance(error, MCPToolError):
        return "执行操作时遇到问题..."
    else:
        return "处理您的消息时出现问题..."
```

## 七、扩展点

### 7.1 添加新的上下文类型
在 `ContextManager.resolve_context_requests()` 添加:
```python
elif kind == 'new_context_type':
    # 实现新的上下文获取逻辑
    resolved[name] = await self._get_new_context(...)
```

### 7.2 添加新的工具验证
在 `ToolExecutor.execute_plan()` 的验证循环中添加:
```python
if needs_verification:
    # 添加新的验证逻辑
    verification_result = await self._verify_new_condition(...)
```

### 7.3 自定义日志输出
在关键位置添加:
```python
logger.info(
    "custom.event",
    trace_id=trace_id,
    custom_field=value,
    duration_ms=int((time.time() - start) * 1000)
)
```

## 八、调试指南

### 8.1 追踪请求流程
```bash
# 通过trace_id追踪完整流程
grep "trace_id=92f2a6cc-2ded-4a51-9652-96702cca2c98" logs.txt
```

### 8.2 分析性能瓶颈
```bash
# 查看各步骤耗时
grep "duration_ms" logs.txt | grep "step"

# 查看LLM调用耗时
grep "llm.response.summary" logs.txt | grep "duration_ms"
```

### 8.3 查看思考循环
```bash
# 查看思考轮数
grep "thinking_loop" logs.txt

# 查看每轮的分析内容
grep "analysis.round.started" logs.txt
```

## 九、最佳实践

### 9.1 代码维护
- 保持方法单一职责
- 添加详细的日志输出
- 使用类型注解
- 异常处理要完善

### 9.2 性能优化
- 使用缓存减少重复计算
- 限制思考轮数(≤2)
- 工具调用尽量批量
- 使用聚合查询替代多次查询

### 9.3 调试技巧
- 设置DEBUG=true查看详细日志
- 使用trace_id追踪请求
- 监控duration_ms找瓶颈
- 查看cache命中率优化缓存

---
*Document Version: 1.0*
*Last Updated: 2025.09.29*
*Code Version: V2 Enhanced*
