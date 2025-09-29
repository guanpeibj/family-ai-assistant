FROM python:3.12-slim

# 设置时区为东八区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 使用国内镜像源加速 APT
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list || true && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list || true && \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources || true && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources || true

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple/ uv

# 复制依赖定义并安装
COPY . .
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ -e .

# 设置 FastEmbed 模型缓存目录
ENV FASTEMBED_CACHE_PATH="/data/fastembed_cache"
RUN mkdir -p /data/fastembed_cache

# 预下载 FastEmbed 模型，避免运行时下载失败
RUN . .venv/bin/activate && \
    python scripts/preload_fastembed.py || \
    echo "Model pre-download failed, will retry at runtime"

# 设置 PATH 以使用虚拟环境
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 默认启动 API 服务；MCP 服务会在 compose 中覆盖该命令
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
