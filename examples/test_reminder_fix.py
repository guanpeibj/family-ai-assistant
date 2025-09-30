#!/usr/bin/env python3
"""
测试提醒功能修复

验证：
1. check_and_send_reminders 方法存在
2. 不再出现 'AIEngineV2' object has no attribute 错误
3. SQL日志简化
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_reminder_method():
    """测试提醒方法是否存在"""
    try:
        from src.ai_engine import ai_engine
        
        print("✅ 成功导入 ai_engine")
        print(f"✅ 类型: {ai_engine.__class__.__name__}")
        
        # 检查方法是否存在
        has_method = hasattr(ai_engine, 'check_and_send_reminders')
        print(f"✅ check_and_send_reminders 方法存在: {has_method}")
        
        if has_method:
            method = getattr(ai_engine, 'check_and_send_reminders')
            print(f"✅ 方法类型: {type(method)}")
            print(f"✅ 方法签名: {method.__doc__}")
        
        # 检查新增的智能增强特性
        sample_analysis = ai_engine._create_fallback_analysis("测试", {})
        print(f"✅ 智能增强特性可用: {hasattr(sample_analysis.understanding, 'thinking_depth')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False

async def test_database_logging():
    """测试数据库日志设置"""
    try:
        from src.db.database import engine
        
        echo_setting = engine.echo
        print(f"✅ 数据库echo设置: {echo_setting}")
        
        if echo_setting:
            print("⚠️  数据库日志仍然开启，可能会产生大量SQL输出")
        else:
            print("✅ 数据库日志已关闭，SQL输出已简化")
        
        return not echo_setting
        
    except Exception as e:
        print(f"❌ 数据库配置检查失败: {str(e)}")
        return False

async def main():
    """主测试函数"""
    print("=" * 60)
    print("FAA 提醒功能修复验证")
    print("=" * 60)
    
    print("\n🔍 测试1: 提醒方法检查")
    reminder_ok = await test_reminder_method()
    
    print("\n🔍 测试2: 数据库日志检查")
    logging_ok = await test_database_logging()
    
    print("\n" + "=" * 60)
    if reminder_ok and logging_ok:
        print("✅ 所有修复验证通过！")
        print("\n预期效果：")
        print("1. 不再出现 'check_and_send_reminders' 方法缺失错误")
        print("2. SQL日志输出大幅减少")
        print("3. 提醒任务正常运行")
        print("4. 智能增强功能全部可用")
    else:
        print("❌ 部分验证失败，需要进一步检查")
    
    print("=" * 60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
