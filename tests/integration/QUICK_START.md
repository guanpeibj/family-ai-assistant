# FAA 集成测试快速使用指南

## 🚀 5分钟快速上手

### 1. 环境检查

```bash
# 1) 确保在项目根目录
cd /Users/guanpei/Develop/family-ai-assistant

# 2) 确保服务运行
docker-compose ps
# 应该看到 faa-postgres 和 faa-mcp 在运行

# 3) 如果服务未运行，启动它们
docker-compose up -d
```

### 2. 运行第一个测试

```bash
# 运行P0核心测试（推荐首次运行）
python tests/integration/run_tests.py --priority P0
```

### 3. 查看结果

测试会输出详细的执行过程和结果：

```
╔══════════════════════════════════════════════════════════════╗
║ 测试套件: 基础记账功能                        TC001-TC008 ║
╚══════════════════════════════════════════════════════════════╝

================================================================================
[TC001] 简单记账 - 完整信息
================================================================================
输入：今天买菜花了80元

AI回复：
✅ 已记录餐饮支出80元

耗时：3.45秒
✅ 测试通过
```

## 📋 常用命令

```bash
# 运行特定优先级
python tests/integration/run_tests.py --priority P0  # 核心功能
python tests/integration/run_tests.py --priority P1  # 重要功能
python tests/integration/run_tests.py --priority P2  # 增强功能

# 运行所有测试
python tests/integration/run_tests.py --all

# 运行单个测试套件
python tests/integration/run_tests.py --suite accounting
python tests/integration/run_tests.py --suite budget
python tests/integration/run_tests.py --suite query

# 直接运行测试文件
python tests/integration/test_p0_accounting.py
python tests/integration/test_p0_budget.py
```

## 🎯 测试覆盖范围

### P0 - 核心必测（40个用例）
**运行时间**: ~15-20分钟

- ✅ 基础记账（8个）
- ✅ 预算管理（4个）
- ✅ 基础查询（4个）
- ✅ 健康记录（3个）
- ✅ 基础提醒（4个）
- ✅ 信息管理（4个）
- ✅ 澄清功能（4个）
- ✅ 数据准确性（7个）
- ✅ 日常场景（5个）

### P1 - 重要功能（部分实现）
**运行时间**: ~20-25分钟

- ✅ 高级查询（4个）
- ✅ 可视化（3个）
- ✅ 健康分析（6个）
- ✅ 提醒管理（5个）
- ⏳ 语音输入（待实现）
- ⏳ 图片识别（待实现）
- ⏳ 复杂查询（待实现）
- ⏳ 主动分析（待实现）

### P2 - 增强功能（部分实现）
**运行时间**: ~15-20分钟

- ✅ 综合场景（4个）
- ⏳ 其他增强功能（待实现）

## 🔍 测试结果解读

### 成功的测试

```
✅ 测试通过
数据验证: ✅ 所有字段准确
```

### 失败的测试

```
❌ 测试失败
   - 缺少关键词：预算
   - 数据库验证失败：未找到记录
```

### 警告

```
⚠️ 性能未达标：6.8秒 >= 5秒
```

## 📊 测试报告

测试报告保存在 `tests/integration/reports/`:

```bash
# 查看最新报告
ls -lt tests/integration/reports/ | head -5

# 查看JSON报告
cat tests/integration/reports/test_report_P0_*.json | jq
```

## 🛠️ 故障排查

### 问题1: "MCP服务初始化失败"

**解决方案**:
```bash
# 检查MCP服务状态
docker-compose ps faa-mcp

# 重启MCP服务
docker-compose restart faa-mcp

# 查看MCP日志
docker-compose logs faa-mcp
```

### 问题2: "数据库连接失败"

**解决方案**:
```bash
# 检查PostgreSQL
docker-compose ps faa-postgres

# 重启数据库
docker-compose restart faa-postgres

# 测试连接
psql -U postgres -h localhost -d faa -c "SELECT 1;"
```

### 问题3: "AI响应超时"

**解决方案**:
```bash
# 检查API密钥
echo $OPENAI_API_KEY

# 检查网络
curl https://api.openai.com/v1/models

# 重新运行单个失败的测试
python tests/integration/test_p0_accounting.py
```

### 问题4: "某个测试用例一直失败"

**调试步骤**:
```bash
# 1. 单独运行该测试
python tests/integration/test_p0_xxx.py

# 2. 开启调试模式
export DEBUG=true
python tests/integration/test_p0_xxx.py

# 3. 查看数据库中的实际数据
psql -U postgres -h localhost -d faa
\x
SELECT * FROM memories WHERE user_id LIKE 'test_user_integration_%' ORDER BY created_at DESC LIMIT 5;
```

## 📝 查看测试数据

```bash
# 连接数据库
psql -U postgres -h localhost -d faa

# 查看测试用户
SELECT DISTINCT user_id FROM memories WHERE user_id LIKE 'test_user_%';

# 查看某个测试套件的数据
SELECT 
  id, 
  LEFT(content, 50) as content_preview,
  ai_understanding->>'type' as type,
  ai_understanding->>'category' as category,
  amount,
  created_at
FROM memories 
WHERE user_id = 'test_user_integration_p0_accounting'
ORDER BY created_at DESC
LIMIT 10;
```

## 🧹 清理测试数据

```bash
# 方式1: SQL清理（推荐）
psql -U postgres -h localhost -d faa << EOF
DELETE FROM memories WHERE user_id LIKE 'test_user_integration_%';
DELETE FROM reminders WHERE user_id LIKE 'test_user_integration_%';
DELETE FROM interactions WHERE user_id LIKE 'test_user_integration_%';
SELECT 'Test data cleaned';
EOF

# 方式2: 在测试中调用cleanup（代码中）
# await tester.cleanup()
```

## 📚 进阶使用

### 自定义测试配置

在测试文件中修改：

```python
class TestP0Accounting(IntegrationTestBase):
    def __init__(self):
        super().__init__(test_suite_name="custom_name")
        # 自定义配置
```

### 添加数据库验证

```python
async def verify():
    # 自定义验证逻辑
    return await self.verify_memory_exists(
        filters={"type": "expense", "amount": 100},
        min_count=1
    )

await self.run_test(
    test_id="TC001",
    test_name="测试名称",
    message="用户输入",
    verify_db=verify
)
```

### 查看详细输出

```python
# 在测试文件中添加
print(f"调试信息：{variable}")
logger.info("custom_log", key="value")
```

## 🎓 最佳实践

### 1. 测试前准备

- ✅ 确保服务正常运行
- ✅ 确认API密钥配置正确
- ✅ 清理旧的测试数据（可选）

### 2. 测试执行

- ✅ 首次运行P0核心测试
- ✅ 逐步运行P1、P2
- ✅ 关注失败的测试用例
- ✅ 查看详细日志分析问题

### 3. 测试后

- ✅ 查看测试报告
- ✅ 分析失败原因
- ✅ 验证数据库数据（可选）
- ✅ 清理测试数据（可选）

### 4. CI/CD集成

```bash
# 在CI管道中
#!/bin/bash
set -e

# 启动服务
docker-compose up -d

# 等待服务就绪
sleep 10

# 运行P0核心测试
python tests/integration/run_tests.py --priority P0

# 检查退出码
if [ $? -eq 0 ]; then
    echo "✅ 测试通过"
    exit 0
else
    echo "❌ 测试失败"
    exit 1
fi
```

## 📞 获取帮助

遇到问题？查看：

1. [详细README](./README.md)
2. [测试用例清单](../../docs/TEST_CASES.md)（如有）
3. [项目架构文档](../../ARCHITECTURE.md)
4. [AI引擎文档](../../docs/AI_ENGINE_TECHNICAL.md)

---

**Happy Testing! 🎉**

祝测试顺利！如有问题，请查看详细文档或联系开发团队。

