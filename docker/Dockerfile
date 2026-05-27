# API image for grounded-rag-assistant.
# Phase 0: just enough to start the FastAPI app and serve /health.
FROM python:3.11-slim

# curl is used by the compose healthcheck pattern and is handy for debugging.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install dependencies first so the layer caches across code changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Application code.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
