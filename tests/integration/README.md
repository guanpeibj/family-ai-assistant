# FAA 集成测试套件

完整的端到端集成测试，验证FAA的实际使用场景。

## 📋 设计原则

本测试套件遵循三个核心原则：

1. **以最终目标为导向**：测试基于 readme.MD 中的实际使用场景
2. **以AI驱动理念为核心**：重点测试AI的理解、决策和执行能力
3. **简洁、直接、稳定**：功能性验证，不过度细化

## 🎯 测试覆盖

### P0 - 核心必测功能（40个用例）

| 测试套件 | 文件 | 用例 | 说明 |
|---------|------|------|------|
| 基础记账 | test_p0_accounting.py | TC001-TC008 | 简单记账、澄清、类目映射、跨月记账 |
| 预算核心 | test_p0_budget.py | TC009-TC013 | 设置预算、查询、预算警告 |
| 基础查询 | test_p0_query.py | TC015-TC018 | 月度查询、按类目/时间/人员查询 |
| 健康记录 | test_p0_health.py | TC026-TC028 | 记录身高体重、多指标体检 |
| 基础提醒 | test_p0_reminder.py | TC038-TC041 | 设置提醒、提前提醒、澄清 |
| 信息管理 | test_p0_info.py | TC052-TC055 | 存储/更新/查询重要信息 |
| 澄清功能 | test_p0_clarification.py | TC070-TC073 | 多字段澄清、多轮对话 |
| 数据准确性 | test_p0_data_accuracy.py | TC090-TC096 | 存储检索更新、时区、日期解析 |
| 日常场景 | test_p0_scenarios.py | TC104-TC109 | 性能测试、日常使用流程 |

### P1 - 重要功能（40个用例）

| 测试套件 | 文件 | 用例 | 说明 |
|---------|------|------|------|
| 高级查询 | test_p1_advanced_query.py | TC019-TC022 | 趋势分析、月度对比、模式识别 |
| 可视化 | test_p1_visualization.py | TC023-TC025 | 饼图、折线图、柱状图 |
| 健康分析 | test_p1_health_analysis.py | TC032-TC037 | 成长曲线、疫苗记录、健康建议 |
| 提醒管理 | test_p1_reminder_management.py | TC044-TC048 | 查询、修改、取消、完成提醒 |
| 语音输入 | test_p1_voice_input.py | TC059-TC062 | 语音记账、口语化理解（待实现） |
| 图片识别 | test_p1_image_recognition.py | TC063-TC066 | 截图识别、小票识别（待实现） |
| 复杂查询 | test_p1_complex_query.py | TC074-TC077 | 多维查询、推理分析（待实现） |
| 主动分析 | test_p1_proactive_analysis.py | TC082-TC085 | 自动警告、异常检测（待实现） |

### P2 - 增强功能（36个用例）

| 测试套件 | 文件 | 用例 | 说明 |
|---------|------|------|------|
| 综合场景 | test_p2_综合场景.py | TC113-TC116 | 生病流程、疫苗流程、旅行场景 |
| 其他P2测试 | - | - | 待实现 |

## 🚀 快速开始

### 环境准备

```bash
# 确保已安装依赖
cd /Users/guanpei/Develop/family-ai-assistant
pip install -r requirements.txt

# 确保数据库已启动
docker-compose up -d faa-postgres

# 确保MCP服务已启动
docker-compose up -d faa-mcp
```

### 运行测试

```bash
# 运行P0核心测试（推荐首先运行）
python tests/integration/run_tests.py --priority P0

# 运行P1重要功能测试
python tests/integration/run_tests.py --priority P1

# 运行P2增强功能测试
python tests/integration/run_tests.py --priority P2

# 运行所有测试
python tests/integration/run_tests.py --all

# 运行特定测试套件
python tests/integration/run_tests.py --suite accounting
python tests/integration/run_tests.py --suite budget
python tests/integration/run_tests.py --suite query
```

### 单独运行某个测试文件

```bash
# 运行基础记账测试
python tests/integration/test_p0_accounting.py

# 运行预算管理测试
python tests/integration/test_p0_budget.py

# 其他测试文件同理
```

## 📊 测试报告

测试完成后，报告会自动保存到 `tests/integration/reports/` 目录：

```
reports/
├── test_report_P0_20251010_143022.json
├── test_report_P1_20251010_150145.json
└── test_report_ALL_20251010_153530.json
```

报告格式（JSON）：
```json
{
  "scope": "P0",
  "timestamp": "20251010_143022",
  "start_time": "2025-10-10T14:30:22",
  "end_time": "2025-10-10T14:35:45",
  "results": [...]
}
```

## 🔍 数据隔离机制

### 测试用户ID

所有测试使用 `test_user_integration_` 前缀的用户ID：

- `test_user_integration_p0_accounting`
- `test_user_integration_p0_budget`
- `test_user_integration_p0_query`
- ... 等

### 数据清理

```bash
# 测试默认不清理数据（便于调试）
# 如需手动清理，在测试类中调用：
await tester.cleanup()
```

或直接查询数据库清理：

```sql
-- 清理所有测试数据
DELETE FROM memories WHERE user_id LIKE 'test_user_integration_%';
DELETE FROM reminders WHERE user_id LIKE 'test_user_integration_%';
DELETE FROM interactions WHERE user_id LIKE 'test_user_integration_%';
```

## 📝 测试结果示例

```
╔══════════════════════════════════════════════════════════════════════════════╗
║ 测试套件: 基础记账功能                                        TC001-TC008 ║
╚══════════════════════════════════════════════════════════════════════════════╝

================================================================================
[TC001] 简单记账 - 完整信息
================================================================================
输入：今天买菜花了80元

AI回复：
✅ 已记录餐饮支出80元，本月餐饮支出890元

耗时：3.45秒
✅ 测试通过

================================================================================
测试总结 - p0_accounting
================================================================================
总测试数：15
✅ 通过：14 (93.3%)
❌ 失败：1 (6.7%)
平均耗时：4.23秒

详细结果：
1. ✅ [TC001] 简单记账 - 完整信息 (3.45s)
2. ✅ [TC002] 记账 - 缺少金额（澄清） (2.78s)
...
```

## 🛠️ 扩展测试

### 添加新测试用例

1. 在对应优先级的测试文件中添加方法：

```python
async def test_tcXXX_your_test_name(self):
    """
    TCXXX: 测试名称
    
    验证点：
    1. 验证点1
    2. 验证点2
    """
    await self.run_test(
        test_id="TCXXX",
        test_name="测试名称",
        message="用户输入",
        expected_keywords=["关键词1", "关键词2"],
        verify_db=verify_function  # 可选
    )
```

2. 在测试类的 `main()` 函数中调用：

```python
await tester.test_tcXXX_your_test_name()
```

### 创建新测试套件

1. 创建新文件 `test_pX_new_suite.py`
2. 继承 `IntegrationTestBase`
3. 实现测试方法
4. 在 `run_tests.py` 的 `TEST_SUITES` 中注册

## 📌 注意事项

### 1. 运行顺序

- **首次运行**：建议先运行 P0，确保核心功能正常
- **CI/CD**：每次代码提交运行 P0，定期运行 P0+P1
- **发布前**：运行全量测试（P0+P1+P2）

### 2. 测试数据

- 测试会创建真实的数据库记录
- 使用独立的test用户ID，不影响生产数据
- 默认保留测试数据便于调试

### 3. 性能预期

- P0 全套测试：约15-20分钟
- P1 全套测试：约20-25分钟
- P2 全套测试：约15-20分钟
- 单个测试用例：3-10秒

### 4. AI响应的不确定性

- AI回复可能有变化，关键词验证较宽松
- 重点验证功能实现，而非具体措辞
- 复杂场景可能需要多次运行验证稳定性

## 🐛 故障排查

### 测试失败常见原因

1. **MCP服务未启动**
   ```bash
   docker-compose ps  # 检查服务状态
   docker-compose logs faa-mcp  # 查看MCP日志
   ```

2. **数据库连接失败**
   ```bash
   docker-compose ps faa-postgres
   psql -U postgres -h localhost -d faa  # 测试连接
   ```

3. **AI引擎初始化失败**
   - 检查 `OPENAI_API_KEY` 环境变量
   - 检查网络连接
   - 查看应用日志

4. **某个测试用例失败**
   - 查看详细日志输出
   - 单独运行该测试文件调试
   - 检查数据库中的实际数据

### 日志调试

```bash
# 开启调试模式
export DEBUG=true

# 运行测试
python tests/integration/run_tests.py --priority P0

# 查看详细日志
tail -f logs/faa.log
```

## 📚 参考文档

- [项目核心理念](../../readme.MD)
- [架构设计](../../ARCHITECTURE.md)
- [Prompt管理](../../prompts/family_assistant_prompts.yaml)
- [AI引擎工作流](../../docs/AI_ENGINE_TECHNICAL.md)

## 🤝 贡献指南

欢迎添加新的测试用例！请确保：

1. 测试覆盖真实使用场景
2. 验证点清晰明确
3. 注释详细易懂
4. 遵循现有命名规范
5. 提交前运行测试确保通过

---

**版本**: 1.0.0  
**更新日期**: 2025-10-10  
**维护者**: FAA Development Team

