FROM python:3.12.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 app
WORKDIR /app
COPY python-agent/pyproject.toml python-agent/uv.lock ./
RUN pip install --no-cache-dir uv==0.8.15 \
    && uv sync --frozen --no-dev
COPY python-agent/ ./
RUN mkdir -p /data/generated \
    && chown -R app:app /app /data/generated
USER 10001
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    CODE_OUTPUT_DIR=/data/generated
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
