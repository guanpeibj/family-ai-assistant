FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制MCP服务器代码
COPY . .

CMD ["python", "-m", "family_mcp_server"]