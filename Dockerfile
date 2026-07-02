FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY asgi.py .
COPY db/ db/
COPY scripts/ scripts/

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
    CMD curl -fsS "http://localhost:${PORT:-8080}/v2/health" || exit 1
# Shell form para expandir $PORT: los PaaS (Render/Railway) inyectan un puerto dinámico;
# en local/Fly cae a 8080 por defecto.
# WEB_CONCURRENCY (default 1) permite escalar procesos sin tocar la imagen; ojo:
# cada worker carga su propio modelo de embeddings (~1,5 GB), así que subirlo
# exige dimensionar la RAM del plan. El pipeline pesado del webhook ya no bloquea
# el event loop (corre en el threadpool), así que 1 worker sirve a varios tenants.
CMD ["sh", "-c", "uvicorn asgi:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-1}"]
