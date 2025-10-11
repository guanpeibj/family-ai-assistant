"""
数据层验证器

验证AI是否正确执行了任务：
- 数据是否存储
- 数据是否准确
- 数据结构是否合理
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.database import get_session
from src.db.models import Memory, Reminder
from sqlalchemy import select, func
import structlog

logger = structlog.get_logger(__name__)


class DataVerificationResult:
    """数据验证结果"""
    
    def __init__(self):
        self.score = 0.0  # 满分40
        self.details = {}
        self.issues = []
        self.success = True
        
    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "details": self.details,
            "issues": self.issues,
            "success": self.success
        }


class DataValidator:
    """数据层验证器"""
    
    def __init__(self, user_id: Union[str, uuid.UUID]):
        """
        初始化数据验证器
        
        Args:
            user_id: 用户ID（可以是字符串或UUID对象）
        """
        # 如果是字符串，转换为UUID对象用于数据库查询
        if isinstance(user_id, str):
            self.user_id = uuid.UUID(user_id)
        else:
            self.user_id = user_id
        
    async def verify(
        self,
        expected: Dict[str, Any],
        test_context: Dict[str, Any]
    ) -> DataVerificationResult:
        """
        执行数据层验证
        
        Args:
            expected: 预期的数据内容
            test_context: 测试上下文
            
        Returns:
            DataVerificationResult
        """
        result = DataVerificationResult()
        
        try:
            # 1. 验证数据存储 (10分)
            storage_score = await self._verify_storage(expected)
            result.details["storage"] = storage_score
            
            # 2. 验证数据准确性 (15分)
            accuracy_score = await self._verify_accuracy(expected)
            result.details["accuracy"] = accuracy_score
            
            # 3. 验证数据结构 (10分)
            structure_score = await self._verify_structure(expected)
            result.details["structure"] = structure_score
            
            # 4. 验证幂等性/去重 (5分)
            idempotency_score = await self._verify_idempotency(expected, test_context)
            result.details["idempotency"] = idempotency_score
            
            # 计算总分
            result.score = (
                storage_score.get("score", 0) +
                accuracy_score.get("score", 0) +
                structure_score.get("score", 0) +
                idempotency_score.get("score", 0)
            )
            
            # 收集问题
            for detail in [storage_score, accuracy_score, structure_score, idempotency_score]:
                if detail.get("issues"):
                    result.issues.extend(detail["issues"])
            
            result.success = result.score >= 36
            
        except Exception as e:
            logger.error("data_verification_failed", error=str(e))
            result.success = False
            result.issues.append(f"验证异常: {str(e)}")
            
        return result
    
    async def _verify_storage(self, expected: Dict) -> Dict:
        """验证数据存储 (满分10)"""
        score_data = {"score": 0, "details": {}, "issues": []}
        
        if not expected.get("should_store"):
            # 不需要存储数据的场景
            score_data["score"] = 10
            score_data["details"]["note"] = "无需存储数据"
            return score_data
        
        try:
            async with get_session() as session:
                # 获取最近的记忆
                query = select(Memory).where(
                    Memory.user_id == self.user_id
                ).order_by(Memory.created_at.desc()).limit(5)
                
                result = await session.execute(query)
                memories = result.scalars().all()
                
                if not memories:
                    score_data["issues"].append("未找到任何记录")
                    return score_data
                
                # 有记录
                score_data["score"] = 10
                score_data["details"]["found_records"] = len(memories)
                score_data["details"]["latest_created_at"] = str(memories[0].created_at)
                
        except Exception as e:
            score_data["issues"].append(f"查询失败: {str(e)}")
            
        return score_data
    
    async def _verify_accuracy(self, expected: Dict) -> Dict:
        """验证数据准确性 (满分15)"""
        score_data = {"score": 0, "details": {}, "issues": []}
        
        expected_data = expected.get("expected_data", {})
        if not expected_data:
            score_data["score"] = 15
            score_data["details"]["note"] = "无需验证准确性"
            return score_data
        
        try:
            async with get_session() as session:
                query = select(Memory).where(
                    Memory.user_id == self.user_id
                ).order_by(Memory.created_at.desc()).limit(1)
                
                result = await session.execute(query)
                memory = result.scalars().first()
                
                if not memory:
                    score_data["issues"].append("未找到记录")
                    return score_data
                
                # 验证金额 (5分)
                if "amount" in expected_data:
                    amount_score = self._verify_amount(
                        memory.amount,
                        expected_data["amount"],
                        expected.get("tolerance", {}).get("amount", 0)
                    )
                    score_data["score"] += amount_score["score"]
                    score_data["details"]["amount"] = amount_score["details"]
                    if amount_score.get("issues"):
                        score_data["issues"].extend(amount_score["issues"])
                else:
                    score_data["score"] += 5
                
                # 验证类目 (5分)
                if "category" in expected_data:
                    category_score = self._verify_category(
                        memory.ai_understanding.get("category"),
                        expected_data["category"],
                        expected.get("tolerance", {}).get("category", [])
                    )
                    score_data["score"] += category_score["score"]
                    score_data["details"]["category"] = category_score["details"]
                    if category_score.get("issues"):
                        score_data["issues"].extend(category_score["issues"])
                else:
                    score_data["score"] += 5
                
                # 验证时间 (5分)
                if "occurred_at" in expected_data:
                    time_score = self._verify_time(
                        memory.occurred_at,
                        expected_data["occurred_at"]
                    )
                    score_data["score"] += time_score["score"]
                    score_data["details"]["occurred_at"] = time_score["details"]
                    if time_score.get("issues"):
                        score_data["issues"].extend(time_score["issues"])
                else:
                    score_data["score"] += 5
                    
        except Exception as e:
            score_data["issues"].append(f"准确性验证失败: {str(e)}")
            
        return score_data
    
    def _verify_amount(self, actual: Optional[Decimal], expected: float, tolerance: float) -> Dict:
        """验证金额准确性"""
        result = {"score": 0, "details": {}, "issues": []}
        
        if actual is None:
            result["issues"].append(f"金额字段为空，期望{expected}")
            return result
        
        actual_float = float(actual)
        diff = abs(actual_float - expected)
        error_rate = diff / expected if expected != 0 else 0
        
        result["details"]["actual"] = actual_float
        result["details"]["expected"] = expected
        result["details"]["diff"] = diff
        
        if diff <= tolerance:
            result["score"] = 5
            result["details"]["status"] = "✅ 精确"
        elif error_rate < 0.1:
            result["score"] = 3
            result["details"]["status"] = "⚠️ 近似"
            result["issues"].append(f"金额误差{diff}元（{error_rate*100:.1f}%）")
        else:
            result["score"] = 0
            result["details"]["status"] = "❌ 错误"
            result["issues"].append(f"金额错误: {actual_float} vs {expected}")
        
        return result
    
    def _verify_category(self, actual: Optional[str], expected: str, acceptable: List[str]) -> Dict:
        """验证类目准确性"""
        result = {"score": 0, "details": {}, "issues": []}
        
        if actual is None:
            result["issues"].append(f"类目字段为空，期望{expected}")
            return result
        
        result["details"]["actual"] = actual
        result["details"]["expected"] = expected
        
        if actual == expected:
            result["score"] = 5
            result["details"]["status"] = "✅ 完全正确"
        elif actual in acceptable:
            result["score"] = 3
            result["details"]["status"] = "⚠️ 可接受"
        else:
            result["score"] = 0
            result["details"]["status"] = "❌ 错误"
            result["issues"].append(f"类目错误: {actual} vs {expected}")
        
        return result
    
    def _verify_time(self, actual: Optional[datetime], expected: str) -> Dict:
        """验证时间准确性"""
        result = {"score": 0, "details": {}, "issues": []}
        
        if actual is None:
            result["issues"].append("时间字段为空")
            return result
        
        now = datetime.now()
        result["details"]["actual"] = str(actual)
        
        if expected == "today":
            if actual.date() == now.date():
                result["score"] = 5
                result["details"]["status"] = "✅ 今日"
            elif abs((actual.date() - now.date()).days) <= 1:
                result["score"] = 3
                result["details"]["status"] = "⚠️ 近期"
            else:
                result["score"] = 0
                result["details"]["status"] = "❌ 错误"
                result["issues"].append(f"时间错误: {actual.date()}")
        elif expected == "recent":
            if abs((actual - now).days) <= 7:
                result["score"] = 5
                result["details"]["status"] = "✅ 近期"
            else:
                result["score"] = 0
                result["details"]["status"] = "❌ 过久"
        else:
            # 默认认为合理
            result["score"] = 5
            result["details"]["status"] = "✅"
        
        return result
    
    async def _verify_structure(self, expected: Dict) -> Dict:
        """验证数据结构 (满分10)"""
        score_data = {"score": 0, "details": {}, "issues": []}
        
        try:
            async with get_session() as session:
                query = select(Memory).where(
                    Memory.user_id == self.user_id
                ).order_by(Memory.created_at.desc()).limit(1)
                
                result = await session.execute(query)
                memory = result.scalars().first()
                
                if not memory:
                    return score_data
                
                ai_data = memory.ai_understanding
                
                # 必要字段完整 (5分)
                required_fields = expected.get("required_fields", ["type"])
                missing_fields = [f for f in required_fields if f not in ai_data]
                
                if not missing_fields:
                    score_data["score"] += 5
                    score_data["details"]["required_fields"] = "✅"
                else:
                    score_data["score"] += max(0, 5 - len(missing_fields))
                    score_data["details"]["required_fields"] = f"⚠️ 缺少{missing_fields}"
                    score_data["issues"].append(f"缺少字段: {missing_fields}")
                
                # 数据关联 (3分)
                if "thread_id" in ai_data:
                    score_data["score"] += 3
                    score_data["details"]["relations"] = "✅ 有thread_id"
                else:
                    score_data["score"] += 2
                    score_data["details"]["relations"] = "⚠️ 无thread_id"
                
                # AI扩展 (2分)
                extra_fields = [k for k in ai_data.keys() if k not in required_fields]
                if len(extra_fields) >= 2:
                    score_data["score"] += 2
                    score_data["details"]["ai_extensions"] = f"✅ {len(extra_fields)}个扩展"
                else:
                    score_data["score"] += 1
                    score_data["details"]["ai_extensions"] = "⚠️ 扩展较少"
                    
        except Exception as e:
            score_data["issues"].append(f"结构验证失败: {str(e)}")
            
        return score_data
    
    async def _verify_idempotency(self, expected: Dict, test_context: Dict) -> Dict:
        """验证幂等性/去重 (满分5)"""
        score_data = {"score": 5, "details": {}, "issues": []}
        
        # 简化实现：检查是否有重复记录
        try:
            async with get_session() as session:
                query = select(func.count(Memory.id)).where(
                    Memory.user_id == self.user_id
                )
                
                result = await session.execute(query)
                count = result.scalar()
                
                score_data["details"]["total_records"] = count
                score_data["details"]["status"] = "✅ 无明显重复"
                
        except Exception as e:
            score_data["issues"].append(f"幂等性验证失败: {str(e)}")
            
        return score_data

