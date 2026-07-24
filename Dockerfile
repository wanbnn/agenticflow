FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENTIC_FLOW_DATA_DIR=/app/data

WORKDIR /app

RUN groupadd --system agentic && useradd --system --gid agentic --home /app agentic

COPY pyproject.toml README.md ./
COPY agentic_flow ./agentic_flow

RUN python -m pip install --upgrade pip && \
    python -m pip install .

RUN mkdir -p /app/data && chown -R agentic:agentic /app

USER agentic

EXPOSE 16777

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:16777/health', timeout=3)"

CMD ["python", "-m", "agentic_flow.main"]
