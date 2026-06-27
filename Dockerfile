FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY api.py .
COPY asgi.py .
COPY db/ db/
COPY scripts/ scripts/

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8080/v2/health || exit 1
CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8080"]
