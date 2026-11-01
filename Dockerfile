# 云上形态：一个镜像同时承载 API 与演示页，环境变量决定后端实现。
# 构建：docker build -t medpal-cloud:0.1.0 .
# 运行：docker run -p 8000:8000 -e MEDPAL_LLM=offline -v $PWD/data:/app/data medpal-cloud:0.1.0
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/core ./packages/core
COPY apps ./apps
RUN pip install --no-cache-dir -e .

COPY data ./data
COPY eval ./eval
COPY tools ./tools
COPY tests ./tests

# 数据落在挂载卷上；容器重建不丢本体与决策链
ENV MEDPAL_DATA_DIR=/app/data
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# 默认单进程；上 CCE 时按副本数横向扩，状态都在 GaussDB / OBS 上
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
