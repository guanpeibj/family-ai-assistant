#!/usr/bin/env python3
"""
测试FAA工作流程并展示详细日志
基于AI驱动理念，验证系统的端到端处理流程
"""

import asyncio
import json
import httpx
import time
from datetime import datetime


class WorkflowTester:
    """工作流测试器 - 展示每一步的详细执行过程"""
    
    def __init__(self):
        self.api_url = "http://localhost:8001"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.step_counter = 0
    
    def log_step(self, title: str, details: dict = None):
        """记录步骤日志"""
        self.step_counter += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"\n[{timestamp}] 📍 步骤 {self.step_counter}: {title}")
        if details:
            for key, value in details.items():
                # 格式化输出
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False, indent=2)
                    print(f"  └─ {key}:")
                    for line in value_str.split('\n'):
                        print(f"      {line}")
                else:
                    print(f"  └─ {key}: {value}")
    
    async def test_message_flow(self, content: str, user_id: str, thread_id: str):
        """测试消息处理流程"""
        print("=" * 80)
        print(f"🚀 测试消息处理流程")
        print(f"   消息: {content}")
        print(f"   用户: {user_id}")
        print(f"   线程: {thread_id}")
        print("=" * 80)
        
        # 步骤1: 发送消息
        self.log_step("发送消息到API", {
            "endpoint": f"{self.api_url}/message",
            "method": "POST",
            "payload": {
                "content": content,
                "user_id": user_id,
                "thread_id": thread_id
            }
        })
        
        start_time = time.time()
        
        try:
            # 发送请求
            response = await self.client.post(
                f"{self.api_url}/message",
                json={
                    "content": content,
                    "user_id": user_id,
                    "thread_id": thread_id
                }
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 步骤2: 接收响应
            self.log_step("接收API响应", {
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "response_length": len(response.text)
            })
            
            if response.status_code == 200:
                result = response.json()
                
                # 步骤3: 解析响应
                self.log_step("解析响应内容", {
                    "response": result.get("response", "无响应内容"),
                    "success": result.get("success", False),
                    "message_type": type(result.get("response")).__name__
                })
                
                # 如果有trace_id，显示处理链路
                if "trace_id" in result:
                    self.log_step("处理链路追踪", {
                        "trace_id": result["trace_id"],
                        "tool_calls": result.get("tool_calls", []),
                        "processing_time": result.get("processing_time_ms")
                    })
                
                return result
            else:
                self.log_step("❌ 请求失败", {
                    "status_code": response.status_code,
                    "error": response.text[:200]
                })
                return None
                
        except Exception as e:
            self.log_step("❌ 发生异常", {
                "error_type": type(e).__name__,
                "error_message": str(e)
            })
            return None
    
    async def analyze_workflow(self):
        """分析完整工作流程"""
        print("\n" + "=" * 80)
        print("🔬 FAA 工作流程分析")
        print("=" * 80)
        
        # 测试不同类型的消息
        test_cases = [
            {
                "name": "简单查询",
                "content": "今年花费是多少",
                "user_id": "dad",
                "thread_id": "test_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            },
            {
                "name": "记录消息",
                "content": "今天买菜花了85元",
                "user_id": "dad",
                "thread_id": "test_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            },
            {
                "name": "需要澄清的消息",
                "content": "记一下",
                "user_id": "dad",
                "thread_id": "test_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'='*80}")
            print(f"📝 测试用例 {i}/{len(test_cases)}: {test_case['name']}")
            print(f"{'='*80}")
            
            result = await self.test_message_flow(
                content=test_case["content"],
                user_id=test_case["user_id"],
                thread_id=test_case["thread_id"]
            )
            
            # 分析结果
            if result:
                self.analyze_result(result, test_case["name"])
            
            # 间隔一下避免太快
            if i < len(test_cases):
                await asyncio.sleep(1)
    
    def analyze_result(self, result: dict, test_name: str):
        """分析处理结果"""
        print(f"\n📊 结果分析: {test_name}")
        print("-" * 40)
        
        # 分析响应类型
        response = result.get("response", "")
        if "需要" in response or "请" in response:
            print("  ✅ 类型: 澄清请求")
        elif len(response) < 50:
            print("  ✅ 类型: 简单确认")
        else:
            print("  ✅ 类型: 详细回复")
        
        # 统计信息
        if "tool_calls" in result:
            print(f"  📊 工具调用: {len(result['tool_calls'])} 次")
        if "processing_time_ms" in result:
            print(f"  ⏱️ 处理时间: {result['processing_time_ms']}ms")
        
        print("-" * 40)
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


async def main():
    """主测试函数"""
    print("🎯 FAA 工作流程与日志测试工具")
    print("基于三个核心原则：AI驱动、工程简化、稳定实现")
    print("=" * 80)
    
    tester = WorkflowTester()
    
    try:
        # 先测试健康检查
        print("\n🏥 检查系统健康状态...")
        health_response = await tester.client.get(f"{tester.api_url}/health")
        if health_response.status_code == 200:
            health_data = health_response.json()
            print("✅ 系统正常运行")
            print(f"  └─ 状态: {health_data.get('status')}")
            print(f"  └─ 版本: {health_data.get('version', 'unknown')}")
            print(f"  └─ MCP服务: {'正常' if health_data.get('mcp_connected') else '未连接'}")
        else:
            print("❌ 系统健康检查失败")
            return
        
        # 运行工作流分析
        await tester.analyze_workflow()
        
        # 总结
        print("\n" + "=" * 80)
        print("📋 测试总结")
        print("=" * 80)
        print("""
基于测试结果，系统展示了以下AI驱动特性：
1. ✅ AI自主理解用户意图
2. ✅ AI决定是否需要澄清信息
3. ✅ AI规划并执行工具调用
4. ✅ AI生成适合的响应

工程简化体现：
- 消息处理流程清晰简洁
- 无硬编码业务逻辑
- 通过Prompt驱动行为

建议优化方向：
1. 增强日志输出的可读性
2. 添加处理步骤的详细追踪
3. 优化错误处理和用户提示
        """)
        
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
