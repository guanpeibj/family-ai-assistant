"""
Prompt版本管理器 - 支持动态加载和切换prompt版本
"""
import yaml
import os
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class PromptManager:
    """管理不同版本的AI提示词"""
    
    def __init__(self, prompt_file: str = "prompts/family_assistant_prompts.yaml"):
        self.prompt_file = prompt_file
        self.prompts: Dict[str, Any] = {}
        self.current_version: str = "v1_basic"
        self._load_prompts()
    
    def _load_prompts(self):
        """从YAML文件加载prompts"""
        try:
            # 获取项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            prompt_path = os.path.join(project_root, self.prompt_file)
            
            if not os.path.exists(prompt_path):
                logger.warning(f"Prompt file not found: {prompt_path}, using defaults")
                self._use_defaults()
                return
            
            with open(prompt_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            self.prompts = data.get('prompts', {})
            self.current_version = data.get('current', 'v1_basic')
            
            # 验证当前版本是否存在
            if self.current_version not in self.prompts:
                logger.warning(f"Current version {self.current_version} not found, using v1_basic")
                self.current_version = 'v1_basic'
            
            logger.info(f"Loaded prompt version: {self.current_version}")
            
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            self._use_defaults()
    
    def _use_defaults(self):
        """使用默认的prompts"""
        self.prompts = {
            'v1_basic': {
                'name': '默认版本',
                'system': """
你是一个贴心的家庭AI助手，专门服务于一个有多个孩子的家庭。

你的核心能力：
1. 记账管理：识别并记录家庭收支，提供统计分析和预算建议
2. 健康追踪：记录家人健康数据（身高、体重、疫苗等），跟踪变化趋势
3. 杂事提醒：管理日常事务，及时提醒重要事项

回复原则：
- 温馨友好，像家人般关怀
- 简洁实用，不说废话
- 主动提供有价值的统计和建议
- 记住这是一个有多个孩子的家庭，关注协助和支持妈妈

信息理解指南：
- "今天/昨天/上周"等时间表达要转换为具体日期
- 识别家庭成员：儿子、女儿（大女儿、二女儿）、妻子、我/老公
- 支出自动分类：餐饮、购物、交通、医疗、教育、日用品等
- 如果提到"更新"或"改为"，要覆盖之前的记录

你有以下工具可以使用：
- store: 存储任何重要信息（支出、收入、健康数据、杂事等）
- search: 查找历史记录
- aggregate: 统计分析数据（求和、计数、平均值等）
- schedule_reminder: 设置提醒
- get_pending_reminders: 查看待发送提醒
- mark_reminder_sent: 标记提醒已发送
多模态与附件使用指南：
- 你可能会收到 context.attachments 列表，其中包含 type/mime/path/size/original_name 以及衍生信息（transcription/ocr_text/vision_summary）。
- 优先利用 transcription/ocr_text/vision_summary 来理解图片/语音的含义；当信息不足时，先澄清再行动。
- 对于来自同一对话线程的多轮补充，请使用 thread_id 进行关联。
""",
                'understanding': '',
                'response_generation': '',
                'tool_planning': """
你是一个工具编排器。根据理解结果与上下文，产出一个 JSON：{ "steps": [ {"tool": string, "args": object} ... ] }。

可用工具：
- store(args: {content, ai_data, user_id?, embedding?})
- search(args: {query?, user_id?, filters?, query_embedding?})
- aggregate(args: {user_id?, operation, field?, filters?})
- schedule_reminder(args: {memory_id, remind_at})
- get_pending_reminders(args: {user_id})
- mark_reminder_sent(args: {reminder_id})
 - render_chart(args: {type, title, x, series, style?})

通用规则：
1) 仅输出JSON，不要解释。
2) 如需存储，ai_data 应合并理解出的 entities，并尽量包含 occurred_at(ISO)。如上下文含 thread_id，写入 ai_data.thread_id。
3) 若后续需要对刚存储的记录设置提醒，可在 schedule_reminder.args.memory_id 使用占位符 "$LAST_STORE_ID"。
4) 查询/聚合时，请在 filters 中明确 date_from/date_to/min_amount/max_amount/person/metric 等条件；如需语义检索可给出 query。
5) 若无需动作，返回 {"steps": []}。

统计与图表策略：
- 当用户请求“趋势/汇总/占比/对比”时，先使用 aggregate 获取数据。
- 时间序列请使用 filters.group_by=day/week/month；非时间序列可用 filters.group_by_ai_field=某个 ai 字段（如 category/person）。
- 图表类型选择：趋势→line；对比→bar；占比→pie。
- 渲染图表时，x 为横轴标签（时间或类别），series 为数据序列数组（支持多条）。

检索回退策略：
- 无法生成查询向量时，允许仅用 filters 或简短 query，底层可能使用 trigram 近似匹配；必要时分步组合多次 search。
"""
            }
        }
        self.current_version = 'v1_basic'
    
    def get_system_prompt(self) -> str:
        """获取当前版本的系统提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('system', self.prompts['v1_basic']['system'])
    
    def get_understanding_prompt(self) -> str:
        """获取消息理解的提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('understanding', '')
    
    def get_response_prompt(self) -> str:
        """获取回复生成的提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('response_generation', '')
    
    def get_tool_planning_prompt(self) -> str:
        """获取工具编排提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('tool_planning', '')
    
    def switch_version(self, version: str) -> bool:
        """切换到指定版本的prompt"""
        if version in self.prompts:
            self.current_version = version
            logger.info(f"Switched to prompt version: {version}")
            return True
        else:
            logger.warning(f"Prompt version not found: {version}")
            return False
    
    def list_versions(self) -> Dict[str, Dict[str, str]]:
        """列出所有可用的prompt版本"""
        return {
            version: {
                'name': data.get('name', version),
                'description': data.get('description', '')
            }
            for version, data in self.prompts.items()
        }
    
    def reload(self):
        """重新加载prompt配置"""
        logger.info("Reloading prompt configuration")
        self._load_prompts()


# 全局实例
prompt_manager = PromptManager() 