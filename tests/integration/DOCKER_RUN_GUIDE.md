# 在Docker容器内运行集成测试指南

## 问题诊断

刚才运行`run_tests.py`时报错：
```
ImportError: cannot import name 'async_session' from 'src.db.database'
```

**原因**：`database.py`导出的是`get_session`而非`async_session`

**解决方案**：已修复`base.py`中的导入

---

## ✅ 正确的Docker运行方式

### 方式1：在faa-api容器内运行（推荐）

```bash
# 进入容器
docker-compose exec faa-api bash

# 在容器内运行测试
cd /app
python tests/integration/run_tests.py --priority P0
```

### 方式2：使用docker-compose run（独立容器）

```bash
# 运行P0测试
docker-compose run --rm faa-api python tests/integration/run_tests.py --priority P0

# 运行P1测试
docker-compose run --rm faa-api python tests/integration/run_tests.py --priority P1

# 运行所有测试
docker-compose run --rm faa-api python tests/integration/run_tests.py --all
```

### 方式3：在宿主机运行（需要配置）

```bash
# 1. 确保环境变量正确
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/faa"
export OPENAI_API_KEY="your-key"
export MCP_SERVER_URL="http://localhost:8001"

# 2. 确保服务在运行
docker-compose ps

# 3. 运行测试
python tests/integration/run_tests.py --priority P0
```

---

## 🔍 环境检查清单

### 1. 检查服务状态

```bash
# 检查所有服务
docker-compose ps

# 应该看到：
# faa-postgres  running  0.0.0.0:5432->5432/tcp
# faa-mcp       running  0.0.0.0:8001->8000/tcp  
# faa-api       running  0.0.0.0:8000->8000/tcp
```

### 2. 检查数据库连接

```bash
# 在容器内测试
docker-compose exec faa-api python -c "
from src.db.database import get_session
import asyncio

async def test():
    async with get_session() as session:
        print('✅ 数据库连接成功')

asyncio.run(test())
"
```

### 3. 检查MCP服务

```bash
# 测试MCP服务
curl http://localhost:8001/tools

# 应该返回工具列表JSON
```

### 4. 检查AI引擎

```bash
# 在容器内测试
docker-compose exec faa-api python -c "
from src.ai_engine import ai_engine
import asyncio

async def test():
    await ai_engine.initialize_mcp()
    print('✅ AI引擎初始化成功')
    await ai_engine.close()

asyncio.run(test())
"
```

---

## 🚀 完整测试流程（Docker环境）

### 步骤1：启动所有服务

```bash
cd /Users/guanpei/Develop/family-ai-assistant

# 启动所有服务
docker-compose up -d

# 等待服务就绪（约10秒）
sleep 10

# 检查服务状态
docker-compose ps
```

### 步骤2：运行测试

```bash
# 方式A：进入容器运行（推荐，便于调试）
docker-compose exec faa-api bash
cd /app
python tests/integration/run_tests.py --priority P0

# 方式B：直接运行（快速）
docker-compose exec faa-api python tests/integration/run_tests.py --priority P0
```

### 步骤3：查看结果

```bash
# 查看测试报告
docker-compose exec faa-api ls -lh tests/integration/reports/

# 查看最新报告
docker-compose exec faa-api cat tests/integration/reports/test_report_P0_*.json | head -100
```

---

## 🐛 常见问题排查

### 问题1：ImportError

```bash
# 症状
ImportError: cannot import name 'async_session'

# 原因
database.py 导出的是 get_session，不是 async_session

# 解决
已修复 base.py 中的导入
```

### 问题2：数据库连接失败

```bash
# 症状
asyncpg.exceptions.ConnectionDoesNotExistError

# 检查
docker-compose ps faa-postgres

# 解决
docker-compose restart faa-postgres
```

### 问题3：MCP服务不可用

```bash
# 症状  
Connection refused to MCP server

# 检查
docker-compose logs faa-mcp

# 解决
docker-compose restart faa-mcp
```

### 问题4：找不到模块

```bash
# 症状
ModuleNotFoundError: No module named 'src'

# 原因
容器内的工作目录不对

# 解决
cd /app  # 确保在/app目录
```

---

## 📝 CI/CD集成示例

### GitHub Actions

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Start services
        run: docker-compose up -d
      
      - name: Wait for services
        run: sleep 15
      
      - name: Run P0 tests
        run: |
          docker-compose exec -T faa-api \
            python tests/integration/run_tests.py --priority P0
      
      - name: Upload test reports
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: tests/integration/reports/
```

### 本地自动化脚本

```bash
#!/bin/bash
# scripts/run_integration_tests.sh

set -e

echo "🚀 启动FAA集成测试"

# 1. 启动服务
echo "1️⃣ 启动服务..."
docker-compose up -d

# 2. 等待就绪
echo "2️⃣ 等待服务就绪..."
sleep 15

# 3. 运行P0测试
echo "3️⃣ 运行P0核心测试..."
docker-compose exec -T faa-api python tests/integration/run_tests.py --priority P0

# 4. 检查结果
if [ $? -eq 0 ]; then
    echo "✅ P0测试通过！"
else
    echo "❌ P0测试失败！"
    exit 1
fi

echo "🎉 测试完成！"
```

---

## 🎯 推荐的运行方式

### 日常开发（交互式）

```bash
# 1. 进入容器（一次）
docker-compose exec faa-api bash

# 2. 在容器内反复测试
cd /app
python tests/integration/run_tests.py --priority P0
python tests/integration/test_p0_accounting.py  # 单个文件
python tests/integration/run_tests.py --suite budget  # 单个套件
```

### CI/CD（自动化）

```bash
# 非交互式运行
docker-compose exec -T faa-api python tests/integration/run_tests.py --priority P0
```

### 本地调试（宿主机）

```bash
# 需要正确配置环境变量
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/faa"
export OPENAI_API_KEY="sk-xxx"
export MCP_SERVER_URL="http://localhost:8001"

python tests/integration/run_tests.py --priority P0
```

---

**总结**：

1. ✅ 当前测试方案已修复导入问题
2. ✅ 推荐在容器内运行（环境最一致）
3. ✅ 支持多种运行方式（灵活）

