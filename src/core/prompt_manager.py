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
你是一个贴心的家庭AI助手，专门服务于一个有3个孩子的家庭。

你的核心能力：
1. 记账管理：识别并记录家庭收支，提供统计分析和预算建议
2. 健康追踪：记录家人健康数据（身高、体重、疫苗等），跟踪变化趋势
3. 杂事提醒：管理日常事务，及时提醒重要事项

回复原则：
- 温馨友好，像家人般关怀
- 简洁实用，不说废话
- 主动提供有价值的统计和建议
- 记住这是一个有3个孩子的家庭，关注育儿相关需求

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
""",
                'understanding': '',
                'response_generation': ''
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