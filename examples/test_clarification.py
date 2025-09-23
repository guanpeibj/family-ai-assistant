#!/usr/bin/env python3
"""
阿福(FAA) 自动询问和确认功能测试脚本
"""
import asyncio
import sys
import os

# 添加src路径以便导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai_engine import AIEngine
from core.config import settings
import json

async def test_clarification_scenarios():
    """测试各种需要澄清的场景"""
    
    print("🧪 测试自动询问和确认功能")
    print("=" * 50)
    
    # 初始化AI引擎
    ai_engine = AIEngine()
    await ai_engine.initialize_mcp()
    
    # 测试场景
    test_cases = [
        {
            "name": "记账缺少金额",
            "message": "记账：买了衣服",
            "expected_clarification": True,
            "expected_missing": ["amount"]
        },
        {
            "name": "记账缺少受益人",
            "message": "给孩子买了衣服100元",
            "expected_clarification": True,
            "expected_missing": ["person"]
        },
        {
            "name": "提醒缺少具体人员",
            "message": "提醒我8月1号给孩子打疫苗",
            "expected_clarification": True,
            "expected_missing": ["person"]
        },
        {
            "name": "健康记录缺少人员",
            "message": "今天量了身高92cm",
            "expected_clarification": True,
            "expected_missing": ["person"]
        },
        {
            "name": "完整记账信息",
            "message": "给大女儿买校服花了160元",
            "expected_clarification": False,
            "expected_missing": []
        },
        {
            "name": "完整健康记录",
            "message": "儿子今天身高92cm",
            "expected_clarification": False,
            "expected_missing": []
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. 测试场景：{test_case['name']}")
        print(f"   输入消息：{test_case['message']}")
        
        try:
            # 处理消息
            response = await ai_engine.process_message(
                content=test_case['message'],
                user_id="test_user_123",
                context={"channel": "test"}
            )
            
            # 获取理解结果（用于调试）
            understanding = await ai_engine._understand_message(
                content=test_case['message'],
                user_id="test_user_123",
                context={"channel": "test"}
            )
            
            print(f"   AI理解：{json.dumps(understanding, ensure_ascii=False, indent=2)}")
            print(f"   AI回复：{response}")
            
            # 验证是否符合预期
            need_clarification = understanding.get('need_clarification', False)
            missing_fields = understanding.get('missing_fields', [])
            
            if need_clarification == test_case['expected_clarification']:
                print(f"   ✅ 澄清需求检测正确")
            else:
                print(f"   ❌ 澄清需求检测错误: 期望 {test_case['expected_clarification']}, 实际 {need_clarification}")
            
            # 检查缺失字段
            if set(missing_fields) >= set(test_case['expected_missing']):
                print(f"   ✅ 缺失字段检测正确")
            else:
                print(f"   ❌ 缺失字段检测错误: 期望 {test_case['expected_missing']}, 实际 {missing_fields}")
                
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
    
    # 测试对话连续性
    print(f"\n🔄 测试对话连续性")
    print("-" * 30)
    
    # 第一步：不完整信息
    print("第一步：发送不完整信息")
    response1 = await ai_engine.process_message(
        content="记账：买了衣服",
        user_id="test_user_456",
        context={"channel": "test"}
    )
    print(f"AI回复1：{response1}")
    
    # 第二步：补充信息
    print("\n第二步：补充缺失信息")
    response2 = await ai_engine.process_message(
        content="120元",
        user_id="test_user_456",
        context={"channel": "test"}
    )
    print(f"AI回复2：{response2}")
    
    await ai_engine.close()
    print(f"\n✅ 测试完成")

if __name__ == "__main__":
    asyncio.run(test_clarification_scenarios()) 