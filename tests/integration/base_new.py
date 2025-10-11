"""
集成测试基础类 V2 - AI驱动的评估系统

核心理念：
1. 不测AI怎么说，测AI做了什么
2. 用AI评估AI，支持能力进化
3. 量化评分，支持AB测试和模型对比

三层验证：
- 数据层 (40分): AI是否正确执行了任务
- 智能层 (40分): AI是否聪明地理解和处理
- 体验层 (20分): AI是否提供了良好的用户体验
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import structlog
import uuid

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
from src.db.database import get_session
from src.db.models import Memory, User, Reminder, Interaction
from sqlalchemy import select, delete

from validators import DataValidator, AIEvaluator, ScoringSystem
from validators.scoring import TestScore

logger = structlog.get_logger(__name__)


class IntegrationTestBase:
    """
    集成测试基类 V2
    
    功能：
    1. 三层验证系统（数据/智能/体验）
    2. 量化评分（0-100分）
    3. AI评估员（用AI评估AI）
    4. 详细报告生成
    5. 支持AB测试和模型对比
    """
    
    # 测试用户UUID命名空间（固定UUID，用于生成确定性的测试用户UUID）
    TEST_USER_NAMESPACE = uuid.UUID('00000000-0000-0000-0000-000000000000')
    
    def __init__(self, test_suite_name: str = "base"):
        """
        初始化测试基类
        
        Args:
            test_suite_name: 测试套件名称
        """
        self.test_suite_name = test_suite_name
        # 使用UUID v5生成确定性的测试用户UUID（基于suite名称）
        self.test_user_uuid = uuid.uuid5(self.TEST_USER_NAMESPACE, f"test_integration_{test_suite_name}")
        # 转换为字符串用于JSON序列化（传递给AI引擎和MCP工具）
        self.test_user_id = str(self.test_user_uuid)
        self.test_scores: List[TestScore] = []
        self.setup_complete = False
        
        # 初始化验证器（传递字符串ID）
        self.data_validator = DataValidator(self.test_user_id)
        self.ai_evaluator = AIEvaluator(use_cache=True)
        
    async def setup(self):
        """
        测试前初始化
        """
        logger.info("test_setup_start", suite=self.test_suite_name)
        
        try:
            # 初始化AI引擎
            if ai_engine.mcp_client is None:
                await ai_engine.initialize_mcp()
            
            # 清理旧数据
            await self._cleanup_test_data()
            
            logger.info("test_setup_complete", suite=self.test_suite_name)
            self.setup_complete = True
            return True
            
        except Exception as e:
            logger.error("test_setup_failed", suite=self.test_suite_name, error=str(e))
            return False
    
    async def teardown(self):
        """测试后清理"""
        logger.info("test_teardown", suite=self.test_suite_name, 
                   test_count=len(self.test_scores))
    
    async def cleanup(self):
        """清理测试数据"""
        await self._cleanup_test_data()
        logger.info("test_data_cleaned", suite=self.test_suite_name)
    
    async def _cleanup_test_data(self):
        """内部方法：清理测试数据"""
        try:
            async with get_session() as session:
                # 使用UUID对象进行数据库查询（SQLAlchemy支持UUID类型）
                # 删除相关数据
                await session.execute(
                    delete(Memory).where(Memory.user_id == self.test_user_uuid)
                )
                await session.execute(
                    delete(Reminder).where(Reminder.memory_id.in_(
                        select(Memory.id).where(Memory.user_id == self.test_user_uuid)
                    ))
                )
                await session.execute(
                    delete(Interaction).where(Interaction.user_id == self.test_user_uuid)
                )
                
                logger.info("test_data_cleanup_complete", 
                          user_id=self.test_user_id,  # 已经是字符串
                          suite=self.test_suite_name)
                    
        except Exception as e:
            logger.error("test_data_cleanup_failed", error=str(e))
    
    async def run_test(
        self, 
        test_id: str,
        test_name: str, 
        message: str,
        expected_behavior: Dict[str, Any],
        data_verification: Optional[Dict[str, Any]] = None,
        intelligence_check: Optional[Dict[str, Any]] = None,
        experience_check: Optional[Dict[str, Any]] = None,
        context: Optional[Dict] = None,
    ) -> TestScore:
        """
        运行单个测试用例 - 完整的三层验证
        
        Args:
            test_id: 测试用例ID（如TC001）
            test_name: 测试名称
            message: 用户输入消息
            expected_behavior: 预期行为描述
            data_verification: 数据层验证规则
            intelligence_check: 智能层验证要点
            experience_check: 体验层验证要点
            context: 额外的上下文信息
        
        Returns:
            TestScore对象，包含完整的评分和分析
        """
        print()
        print("=" * 80)
        print(f"[{test_id}] {test_name}")
        print("=" * 80)
        print(f"📝 输入：{message}")
        print()
        
        start_time = datetime.now()
        
        try:
            # ===== 步骤1：调用AI引擎 =====
            test_context = {
                "channel": "api",
                "thread_id": f"test_thread_{self.test_suite_name}",
                **(context or {})
            }
            
            # 传递字符串格式的user_id给AI引擎（用于JSON序列化）
            response = await ai_engine.process_message(
                content=message,
                user_id=self.test_user_id,  # 已经是字符串
                context=test_context
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print(f"🤖 AI回复：")
            print(response)
            print()
            print(f"⏱️  耗时：{duration:.2f}秒")
            print()
            
            # ===== 步骤2：三层验证 =====
            
            # 2.1 数据层验证 (40分)
            print("📊 数据层验证中...")
            data_result = {"score": 40, "details": {}, "issues": []}
            if data_verification:
                data_validation_result = await self.data_validator.verify(
                    expected=data_verification,
                    test_context=test_context
                )
                data_result = data_validation_result.to_dict()
                print(f"   分数: {data_result['score']:.1f}/40")
            
            # ✅ 成本优化：数据层<90%时跳过AI评估（节省成本）
            data_score_threshold = 36.0  # 90% * 40分
            skip_ai_evaluation = data_result['score'] < data_score_threshold
            
            if skip_ai_evaluation:
                print(f"⚠️  数据层得分过低({data_result['score']:.1f}/40 < {data_score_threshold})")
                print("   跳过智能层和体验层评估（节省成本）")
                
                # 直接给0分，不调用AI评估器
                intelligence_result = {
                    "score": 0,
                    "dimensions": {
                        "intent_understanding": 0,
                        "information_extraction": 0,
                        "context_usage": 0,
                        "response_relevance": 0
                    },
                    "reasoning": "数据层未达标(<90%)，跳过AI评估",
                    "suggestions": ["优先修复数据层问题"]
                }
                
                experience_result = {
                    "score": 0,
                    "dimensions": {
                        "persona_alignment": 0,
                        "language_quality": 0,
                        "information_completeness": 0,
                        "user_friendliness": 0
                    },
                    "reasoning": "数据层未达标(<90%)，跳过AI评估",
                    "suggestions": []
                }
                
            else:
                # 2.2 智能层评估 (40分) - 用AI评估
                print("🧠 智能层评估中...")
                test_case = {
                    "test_id": test_id,
                    "test_name": test_name,
                    "user_input": message,
                    "expected_behavior": expected_behavior
                }
                
                # 获取数据库数据用于评估
                db_data = await self._get_latest_memory_data()
                
                intelligence_evaluation = await self.ai_evaluator.evaluate_intelligence(
                    test_case=test_case,
                    ai_response=response,
                    db_data=db_data
                )
                intelligence_result = intelligence_evaluation.to_dict()
                print(f"   分数: {intelligence_result['score']:.1f}/40")
                
                # 2.3 体验层评估 (20分) - 用AI评估
                print("✨ 体验层评估中...")
                experience_evaluation = await self.ai_evaluator.evaluate_experience(
                    test_case=test_case,
                    ai_response=response
                )
                experience_result = experience_evaluation.to_dict()
                print(f"   分数: {experience_result['score']:.1f}/20")
            
            # ===== 步骤3：计算总分 =====
            # 构建对话记录
            conversation = [
                f"user({self.test_user_id})- {message}",
                f"faa- {response}"
            ]
            
            test_score = ScoringSystem.calculate_test_score(
                test_id=test_id,
                test_name=test_name,
                data_result=data_result,
                intelligence_result=intelligence_result,
                experience_result=experience_result,
                duration=duration,
                conversation=conversation
            )
            
            # 添加到结果列表
            self.test_scores.append(test_score)
            
            # ===== 打印结果 =====
            print()
            print(f"{'='*80}")
            if test_score.success:
                print(f"✅ 测试通过 - 总分: {test_score.total_score:.1f}/100 (等级{test_score.get_grade()})")
            else:
                print(f"❌ 测试失败 - 总分: {test_score.total_score:.1f}/100 (等级{test_score.get_grade()})")
            
            print(f"   数据层: {test_score.data_score:.1f}/40")
            print(f"   智能层: {test_score.intelligence_score:.1f}/40")
            print(f"   体验层: {test_score.experience_score:.1f}/20")
            
            if test_score.issues:
                print()
                print("⚠️  改进建议:")
                for i, issue in enumerate(test_score.issues[:5], 1):  # 最多显示5条
                    print(f"   {i}. {issue}")
            
            print(f"{'='*80}")
            
            return test_score
            
        except Exception as e:
            logger.error("test_execution_failed", test_id=test_id, error=str(e))
            print(f"❌ 测试异常：{e}")
            
            # 创建失败的评分
            duration = (datetime.now() - start_time).total_seconds()
            conversation = [f"user({self.test_user_id})- {message}"]
            
            test_score = TestScore(
                test_id=test_id,
                test_name=test_name,
                data_score=0,
                intelligence_score=0,
                experience_score=0,
                total_score=0,
                data_details={},
                intelligence_details={},
                experience_details={},
                duration=duration,
                success=False,
                issues=[f"执行异常: {str(e)}"],
                conversation=conversation
            )
            
            self.test_scores.append(test_score)
            return test_score
    
    async def _get_latest_memory_data(self) -> Optional[Dict]:
        """获取最新的记忆数据用于评估"""
        try:
            async with get_session() as session:
                # 使用UUID对象进行数据库查询
                query = select(Memory).where(
                    Memory.user_id == self.test_user_uuid
                ).order_by(Memory.created_at.desc()).limit(1)
                
                result = await session.execute(query)
                memory = result.scalars().first()
                
                if memory:
                    return {
                        "id": str(memory.id),
                        "content": memory.content,
                        "ai_understanding": memory.ai_understanding,
                        "amount": float(memory.amount) if memory.amount else None,
                        "occurred_at": str(memory.occurred_at) if memory.occurred_at else None,
                        "created_at": str(memory.created_at)
                    }
                return None
                
        except Exception as e:
            logger.error("get_latest_memory_failed", error=str(e))
            return None
    
    async def run_multi_turn_test(
        self,
        test_id: str,
        test_name: str,
        turns: List[Dict[str, Any]],
        context: Optional[Dict] = None,
        fail_fast: bool = False
    ) -> TestScore:
        """
        运行多轮对话测试
        
        Args:
            test_id: 测试用例ID（如MT001）
            test_name: 测试名称
            turns: 多轮对话列表，每轮包含user_input、expected_behavior、data_verification
            context: 额外的上下文信息
            fail_fast: 如果某轮严重失败(<50%)，是否提前终止（默认False，继续测试）
        
        Returns:
            TestScore对象，汇总所有轮次的评分
        """
        print()
        print("=" * 80)
        print(f"[{test_id}] {test_name} (多轮对话，共{len(turns)}轮)")
        print("=" * 80)
        
        start_time = datetime.now()
        turn_results = []
        
        # ✅ 每个多轮测试使用独立的thread_id，避免污染
        test_context = {
            "channel": "api",
            "thread_id": f"multi_turn_{test_id}_{datetime.now().strftime('%H%M%S')}",
            **(context or {})
        }
        
        # 记录所有轮次的对话
        all_conversations = []
        failed_early = False
        
        try:
            # 逐轮执行
            for i, turn_data in enumerate(turns, 1):
                turn_num = turn_data.get("turn", i)
                user_input = turn_data["user_input"]
                expected_behavior = turn_data["expected_behavior"]
                data_verification = turn_data.get("data_verification")
                
                print(f"\n{'─'*80}")
                print(f"🔄 第{turn_num}轮")
                print(f"{'─'*80}")
                print(f"📝 用户：{user_input}")
                
                # 调用AI引擎
                response = await ai_engine.process_message(
                    content=user_input,
                    user_id=self.test_user_id,
                    context=test_context
                )
                
                print(f"🤖 FAA：{response}")
                
                # 记录对话
                all_conversations.append({
                    "turn": turn_num,
                    "user": user_input,
                    "ai": response
                })
                
                # 数据层验证
                data_result = {"score": 40, "details": {}, "issues": []}
                if data_verification:
                    data_validation_result = await self.data_validator.verify(
                        expected=data_verification,
                        test_context=test_context
                    )
                    data_result = data_validation_result.to_dict()
                    
                    # ✅ 打印每轮的数据验证结果
                    print(f"📊 数据验证：{data_result['score']:.1f}/40", end="")
                    if data_result['score'] >= 36:
                        print(" ✅")
                    elif data_result['score'] >= 30:
                        print(" ⚠️")
                    else:
                        print(" ❌")
                    
                    # ✅ fail_fast：如果某轮严重失败，提前终止
                    if fail_fast and data_result['score'] < 20:  # <50%
                        print(f"⚠️  第{turn_num}轮严重失败，提前终止测试")
                        failed_early = True
                        turn_results.append({
                            "turn": turn_num,
                            "data_score": data_result["score"],
                            "user_input": user_input,
                            "ai_response": response,
                            "early_termination": True
                        })
                        break
                
                turn_results.append({
                    "turn": turn_num,
                    "data_score": data_result["score"],
                    "user_input": user_input,
                    "ai_response": response
                })
            
            # 计算总耗时
            duration = (datetime.now() - start_time).total_seconds()
            
            # ===== 汇总评分 =====
            # 数据层：取所有轮的平均分
            avg_data_score = sum(r["data_score"] for r in turn_results) / len(turn_results)
            
            # 如果提前终止，在issues中记录
            if failed_early:
                print(f"\n⚠️  测试提前终止于第{len(turn_results)}轮")
                avg_data_score = avg_data_score * 0.7  # 提前终止扣30%分数
            
            # 只对最后一轮做完整的三层评估（节省成本）
            last_turn = turn_results[-1]
            last_turn_data = turns[-1]
            
            print(f"\n{'='*80}")
            print(f"💎 对最后一轮进行完整评估...")
            
            # 构建最后一轮的测试用例
            final_test_case = {
                "test_id": test_id,
                "test_name": test_name,
                "user_input": last_turn["user_input"],
                "expected_behavior": last_turn_data["expected_behavior"],
                "multi_turn_context": all_conversations[:-1]  # 前面的对话作为上下文
            }
            
            # 数据层已有分数
            final_data_result = {"score": avg_data_score, "details": {}, "issues": []}
            
            # 决定是否跳过AI评估
            data_score_threshold = 36.0  # 90% * 40分
            skip_ai_evaluation = avg_data_score < data_score_threshold
            
            if skip_ai_evaluation:
                print(f"⚠️  数据层平均得分过低({avg_data_score:.1f}/40 < {data_score_threshold})")
                print("   跳过智能层和体验层评估（节省成本）")
                
                intelligence_result = {
                    "score": 0,
                    "dimensions": {"intent_understanding": 0, "information_extraction": 0, "context_usage": 0, "response_relevance": 0},
                    "reasoning": "数据层未达标(<90%)，跳过AI评估",
                    "suggestions": ["优先修复数据层问题"]
                }
                
                experience_result = {
                    "score": 0,
                    "dimensions": {"persona_alignment": 0, "language_quality": 0, "information_completeness": 0, "user_friendliness": 0},
                    "reasoning": "数据层未达标(<90%)，跳过AI评估",
                    "suggestions": []
                }
            else:
                # 智能层和体验层评估（使用最后一轮的AI回复）
                db_data = await self._get_latest_memory_data()
                
                print("🧠 智能层评估中...")
                intelligence_evaluation = await self.ai_evaluator.evaluate_intelligence(
                    test_case=final_test_case,
                    ai_response=last_turn["ai_response"],
                    db_data=db_data
                )
                intelligence_result = intelligence_evaluation.to_dict()
                print(f"   分数: {intelligence_result['score']:.1f}/40")
                
                print("✨ 体验层评估中...")
                experience_evaluation = await self.ai_evaluator.evaluate_experience(
                    test_case=final_test_case,
                    ai_response=last_turn["ai_response"]
                )
                experience_result = experience_evaluation.to_dict()
                print(f"   分数: {experience_result['score']:.1f}/20")
            
            # 生成完整对话记录（用于报告）
            conversation = []
            for c in all_conversations:
                conversation.append(f"user({self.test_user_id})- {c['user']}")
                conversation.append(f"faa- {c['ai']}")
            
            # 计算总分
            test_score = ScoringSystem.calculate_test_score(
                test_id=test_id,
                test_name=test_name,
                data_result=final_data_result,
                intelligence_result=intelligence_result,
                experience_result=experience_result,
                duration=duration,
                conversation=conversation
            )
            
            # 添加到结果列表
            self.test_scores.append(test_score)
            
            # 打印结果
            print()
            print(f"{'='*80}")
            if test_score.success:
                print(f"✅ 多轮测试通过 - 总分: {test_score.total_score:.1f}/100 (等级{test_score.get_grade()})")
            else:
                print(f"❌ 多轮测试失败 - 总分: {test_score.total_score:.1f}/100 (等级{test_score.get_grade()})")
            
            print(f"   数据层: {test_score.data_score:.1f}/40 (平均)")
            print(f"   智能层: {test_score.intelligence_score:.1f}/40")
            print(f"   体验层: {test_score.experience_score:.1f}/20")
            print(f"   完成轮数: {len(turn_results)}/{len(turns)}")
            print(f"   总耗时: {duration:.1f}秒")
            if failed_early:
                print(f"   ⚠️  提前终止")
            
            if test_score.issues:
                print()
                print("⚠️  改进建议:")
                for i, issue in enumerate(test_score.issues[:5], 1):
                    print(f"   {i}. {issue}")
            
            print(f"{'='*80}")
            
            return test_score
            
        except Exception as e:
            logger.error("multi_turn_test_failed", test_id=test_id, error=str(e))
            print(f"❌ 多轮测试异常：{e}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # 生成对话记录
            conversation = []
            if all_conversations:
                for c in all_conversations:
                    conversation.append(f"user({self.test_user_id})- {c['user']}")
                    conversation.append(f"faa- {c['ai']}")
            
            test_score = TestScore(
                test_id=test_id,
                test_name=test_name,
                data_score=0,
                intelligence_score=0,
                experience_score=0,
                total_score=0,
                data_details={},
                intelligence_details={},
                experience_details={},
                duration=duration,
                success=False,
                issues=[f"多轮测试异常: {str(e)}"],
                conversation=conversation
            )
            
            self.test_scores.append(test_score)
            return test_score
    
    def print_summary(self) -> Dict:
        """
        打印测试总结
        
        Returns:
            总结数据字典
        """
        print()
        print("=" * 80)
        print(f"📊 测试总结 - {self.test_suite_name}")
        print("=" * 80)
        
        if not self.test_scores:
            print("没有测试结果")
            return {}
        
        # 计算总结
        summary = ScoringSystem.calculate_suite_summary(self.test_scores)
        
        # 打印总体统计
        print(f"\n总体统计:")
        print(f"  总测试数: {summary.total_cases}")
        print(f"  ✅ 通过: {summary.passed} ({summary.pass_rate*100:.1f}%)")
        print(f"  ❌ 失败: {summary.failed}")
        print(f"  ⏱️  总耗时: {summary.total_duration:.1f}秒")
        print(f"  📈 平均耗时: {summary.avg_duration:.1f}秒")
        
        # 打印平均分数
        print(f"\n平均分数:")
        print(f"  总分: {summary.avg_total_score:.1f}/100")
        print(f"  数据层: {summary.avg_data_score:.1f}/40")
        print(f"  智能层: {summary.avg_intelligence_score:.1f}/40")
        print(f"  体验层: {summary.avg_experience_score:.1f}/20")
        
        # 打印维度详情
        if summary.dimension_averages:
            print(f"\n维度详情:")
            for dim, score in sorted(summary.dimension_averages.items(), 
                                    key=lambda x: x[1], reverse=True):
                max_score = 10 if "intent" in dim or "information" in dim or "context" in dim or "response" in dim else 5
                print(f"  {dim}: {score:.1f}/{max_score}")
        
        # 打印失败用例
        if summary.failed_cases:
            print(f"\n失败用例 ({len(summary.failed_cases)}):")
            for i, case in enumerate(summary.failed_cases, 1):
                print(f"  {i}. [{case['test_id']}] {case['test_name']} - {case['score']:.1f}分")
                if case['issues']:
                    print(f"     问题: {case['issues'][0]}")
        
        # 打印详细结果
        print(f"\n详细结果:")
        for i, score in enumerate(self.test_scores, 1):
            status = "✅" if score.success else "❌"
            grade = score.get_grade()
            print(f"  {i}. {status} [{score.test_id}] {score.test_name}")
            print(f"     分数: {score.total_score:.1f}/100 (等级{grade})")
            print(f"     数据{score.data_score:.0f} + 智能{score.intelligence_score:.0f} + 体验{score.experience_score:.0f} | 耗时{score.duration:.1f}s")
        
        print("=" * 80)
        print()
        
        return summary.to_dict()
    
    async def get_latest_memory(self, memory_type: Optional[str] = None) -> Optional[Memory]:
        """
        获取最新的记忆记录（兼容旧测试）
        """
        try:
            async with get_session() as session:
                # 使用UUID对象进行数据库查询
                query = select(Memory).where(
                    Memory.user_id == self.test_user_uuid
                ).order_by(Memory.created_at.desc())
                
                if memory_type:
                    query = query.where(
                        Memory.ai_understanding['type'].astext == memory_type
                    )
                
                result = await session.execute(query)
                return result.scalars().first()
                
        except Exception as e:
            logger.error("get_latest_memory_failed", error=str(e))
            return None

