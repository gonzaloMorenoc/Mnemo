# Dockerfile para Hugging Face Spaces (SDK: docker).
# Copia ESTE fichero + README.md a la RAÍZ del repo de tu Space.
# El backend se clona del repo PÚBLICO en build → el Space solo necesita estos 2 ficheros + los secrets.
# Requisitos HF: corre como UID 1000 (non-root), escucha en app_port (8080), disco efímero.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces ejecuta el contenedor como UID 1000 — crea el usuario antes de copiar/descargar.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# Backend desde el repo público. Para fijar una versión: añade `--branch <tag>` o cambia a un commit.
RUN git clone --depth 1 https://github.com/gonzaloMorenoc/Mnemo.git .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Pre-descarga el modelo de embeddings EN BUILD (el disco del Space es efímero;
# así no se re-descarga en cada arranque y el cold start es rápido).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8080
# ${PORT:-8080} por portabilidad; en HF el app_port del README es 8080.
CMD ["sh", "-c", "uvicorn asgi:app --host 0.0.0.0 --port ${PORT:-8080}"]
