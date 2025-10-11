"""
AI评估员

使用AI来评估AI的回复质量：
- 智能层：意图理解、信息提取、上下文运用、回复相关性
- 体验层：人设契合、语言质量、信息完整性、用户友好性
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.llm_client import LLMClient
from src.core.config import settings
import structlog

logger = structlog.get_logger(__name__)


class IntelligenceEvaluationResult:
    """智能层评估结果"""
    
    def __init__(self):
        self.score = 0.0  # 满分40
        self.dimensions = {}
        self.reasoning = ""
        self.suggestions = []
        
    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "dimensions": self.dimensions,
            "reasoning": self.reasoning,
            "suggestions": self.suggestions
        }


class ExperienceEvaluationResult:
    """体验层评估结果"""
    
    def __init__(self):
        self.score = 0.0  # 满分20
        self.dimensions = {}
        self.reasoning = ""
        self.suggestions = []
        
    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "dimensions": self.dimensions,
            "reasoning": self.reasoning,
            "suggestions": self.suggestions
        }


class AIEvaluator:
    """AI评估员"""
    
    def __init__(self, use_cache: bool = True):
        """
        初始化AI评估员
        
        Args:
            use_cache: 是否使用缓存
        """
        # 创建专用的评估器LLM客户端（从配置读取，简洁直接）
        api_key = settings.EVALUATOR_LLM_API_KEY or settings.OPENAI_API_KEY
        
        self.llm_client = LLMClient(
            provider=settings.EVALUATOR_LLM_PROVIDER,
            model=settings.EVALUATOR_LLM_MODEL,
            base_url=settings.EVALUATOR_LLM_BASE_URL,
            api_key=api_key
        )
        self.use_cache = use_cache
        self._cache = {}
        
    async def evaluate_intelligence(
        self,
        test_case: Dict[str, Any],
        ai_response: str,
        db_data: Optional[Dict] = None
    ) -> IntelligenceEvaluationResult:
        """
        评估智能层 (40分)
        
        维度：
        - intent_understanding (10分): 意图理解
        - information_extraction (10分): 信息提取
        - context_usage (10分): 上下文运用
        - response_relevance (10分): 回复相关性
        """
        result = IntelligenceEvaluationResult()
        
        # 构建评估prompt
        prompt = self._build_intelligence_prompt(test_case, ai_response, db_data)
        
        # 检查缓存
        cache_key = self._get_cache_key("intelligence", test_case["test_id"], ai_response)
        if self.use_cache and cache_key in self._cache:
            logger.info("using_cached_intelligence_evaluation", test_id=test_case["test_id"])
            return self._cache[cache_key]
        
        try:
            # 调用评估员（使用gpt-4o-mini降低成本）
            response = await self.llm_client.chat_text(
                system_prompt="你是一个专业的AI评估员，负责评估AI助手的回复质量。请严格按照评分标准进行客观评估。",
                user_prompt=prompt,
                temperature=0.3,  # 低温度保证评分一致性
                max_tokens=1000
            )
            
            # 解析结果
            evaluation = self._parse_evaluation_response(response)
            
            # 填充结果
            result.dimensions = {
                "intent_understanding": evaluation.get("intent_understanding", 5),
                "information_extraction": evaluation.get("information_extraction", 5),
                "context_usage": evaluation.get("context_usage", 5),
                "response_relevance": evaluation.get("response_relevance", 5)
            }
            
            result.score = sum(result.dimensions.values())
            result.reasoning = evaluation.get("reasoning", "")
            result.suggestions = evaluation.get("suggestions", [])
            
            # 缓存结果
            if self.use_cache:
                self._cache[cache_key] = result
                
        except Exception as e:
            logger.error("intelligence_evaluation_failed", error=str(e))
            # 降级：给基础分
            result.dimensions = {
                "intent_understanding": 6,
                "information_extraction": 6,
                "context_usage": 6,
                "response_relevance": 6
            }
            result.score = 24
            result.reasoning = f"评估失败，给基础分: {str(e)}"
            
        return result
    
    async def evaluate_experience(
        self,
        test_case: Dict[str, Any],
        ai_response: str
    ) -> ExperienceEvaluationResult:
        """
        评估体验层 (20分)
        
        维度：
        - persona_alignment (5分): 人设契合度
        - language_quality (5分): 语言质量
        - information_completeness (5分): 信息完整性
        - user_friendliness (5分): 用户友好性
        """
        result = ExperienceEvaluationResult()
        
        # 构建评估prompt
        prompt = self._build_experience_prompt(test_case, ai_response)
        
        # 检查缓存
        cache_key = self._get_cache_key("experience", test_case["test_id"], ai_response)
        if self.use_cache and cache_key in self._cache:
            logger.info("using_cached_experience_evaluation", test_id=test_case["test_id"])
            return self._cache[cache_key]
        
        try:
            # 调用评估员
            response = await self.llm_client.chat_text(
                system_prompt="你是一个专业的AI评估员，负责评估AI助手的用户体验质量。请严格按照评分标准进行客观评估。",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            # 解析结果
            evaluation = self._parse_evaluation_response(response)
            
            # 填充结果
            result.dimensions = {
                "persona_alignment": evaluation.get("persona_alignment", 2.5),
                "language_quality": evaluation.get("language_quality", 2.5),
                "information_completeness": evaluation.get("information_completeness", 2.5),
                "user_friendliness": evaluation.get("user_friendliness", 2.5)
            }
            
            result.score = sum(result.dimensions.values())
            result.reasoning = evaluation.get("reasoning", "")
            result.suggestions = evaluation.get("suggestions", [])
            
            # 缓存结果
            if self.use_cache:
                self._cache[cache_key] = result
                
        except Exception as e:
            logger.error("experience_evaluation_failed", error=str(e))
            # 降级：给基础分
            result.dimensions = {
                "persona_alignment": 3,
                "language_quality": 3,
                "information_completeness": 3,
                "user_friendliness": 3
            }
            result.score = 12
            result.reasoning = f"评估失败，给基础分: {str(e)}"
            
        return result
    
    def _build_intelligence_prompt(
        self,
        test_case: Dict,
        ai_response: str,
        db_data: Optional[Dict]
    ) -> str:
        """构建智能层评估prompt"""
        
        expected = test_case.get("expected_behavior", {})
        
        return f"""你是FAA（家庭AI助手）的专业评估员。请客观评估AI助手在智能层的表现。

【评估原则】
- 客观：基于事实，不带偏好
- 一致：相同表现应得相同分数
- 严格但不苛刻：高标准，但合理

【测试场景】
测试ID: {test_case.get('test_id')}
测试名称: {test_case.get('test_name')}
用户输入: "{test_case.get('user_input')}"

【预期行为】
意图: {expected.get('intent', '未指定')}
关键动作: {', '.join(expected.get('key_actions', []))}
回复应该: {expected.get('response_should', '未指定')}

【AI实际回复】
{ai_response}

【数据库数据】
{json.dumps(db_data, ensure_ascii=False, indent=2) if db_data else '无数据或未提供'}

【评估任务】
请对以下4个维度评分（每项0-10分）：

1. intent_understanding（意图理解，10分）
   - 9-10分：完全理解用户意图
   - 7-8分：基本理解但有小偏差
   - 5-6分：理解不准确
   - 3-4分：理解有误
   - 0-2分：完全误解

2. information_extraction（信息提取，10分）
   - 9-10分：关键信息提取完整准确
   - 7-8分：提取大部分关键信息
   - 5-6分：遗漏部分重要信息
   - 3-4分：提取不准确
   - 0-2分：提取错误

3. context_usage（上下文运用，10分）
   - 9-10分：充分利用历史和家庭信息
   - 7-8分：有运用但不充分
   - 5-6分：基本没用上下文
   - 3-4分：上下文运用不当
   - 0-2分：完全忽略上下文

4. response_relevance（回复相关性，10分）
   - 9-10分：回复完全切题且有价值
   - 7-8分：回复相关但价值一般
   - 5-6分：回复偏题
   - 3-4分：答非所问
   - 0-2分：完全无关

【输出格式】
请严格按JSON格式输出，不要有其他内容：
{{
    "intent_understanding": <分数>,
    "information_extraction": <分数>,
    "context_usage": <分数>,
    "response_relevance": <分数>,
    "reasoning": "<一段话说明评分理由>",
    "suggestions": ["<改进建议1>", "<改进建议2>"]
}}"""
    
    def _build_experience_prompt(
        self,
        test_case: Dict,
        ai_response: str
    ) -> str:
        """构建体验层评估prompt"""
        
        expected = test_case.get("expected_behavior", {})
        
        return f"""你是FAA（家庭AI助手）的专业评估员。请客观评估AI助手在用户体验层的表现。

【FAA人设】
- 角色：忠诚的老管家
- 风格：理性、专业、简洁、精炼、准确、有礼貌
- 态度：尊重和关爱主人家庭
- 特点：贴近真实人类对话，不机械化

【测试场景】
用户输入: "{test_case.get('user_input')}"
预期回复应该: {expected.get('response_should', '未指定')}

【AI实际回复】
{ai_response}

【评估任务】
请对以下4个维度评分（每项0-5分）：

1. persona_alignment（人设契合度，5分）
   - 5分：完全符合"老管家"人设
   - 3-4分：基本符合
   - 1-2分：不太符合
   - 0分：完全不符

2. language_quality（语言质量，5分）
   - 5分：简洁精炼、专业礼貌
   - 3-4分：基本合格
   - 1-2分：啰嗦或不礼貌
   - 0分：语言混乱

3. information_completeness（信息完整性，5分）
   - 5分：该说的都说了，不多不少
   - 3-4分：基本完整
   - 1-2分：遗漏关键反馈
   - 0分：信息严重不完整

4. user_friendliness（用户友好性，5分）
   - 5分：易懂、有用、让人放心
   - 3-4分：基本可用
   - 1-2分：让人困惑
   - 0分：糟糕体验

【输出格式】
请严格按JSON格式输出，不要有其他内容：
{{
    "persona_alignment": <分数>,
    "language_quality": <分数>,
    "information_completeness": <分数>,
    "user_friendliness": <分数>,
    "reasoning": "<一段话说明评分理由>",
    "suggestions": ["<改进建议1>"]
}}"""
    
    def _parse_evaluation_response(self, response: str) -> Dict:
        """解析评估响应"""
        try:
            # 尝试直接解析JSON
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(response[start:end+1])
                except json.JSONDecodeError:
                    pass
            
            logger.warning("failed_to_parse_evaluation", response=response)
            return {}
    
    def _get_cache_key(self, layer: str, test_id: str, response: str) -> str:
        """生成缓存key"""
        import hashlib
        response_hash = hashlib.md5(response.encode()).hexdigest()[:8]
        return f"{layer}_{test_id}_{response_hash}"

