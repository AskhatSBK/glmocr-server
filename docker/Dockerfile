# ============================================================
# GLM-OCR Production Server — Dockerfile
# Build:  docker build -t glmocr-server .
# Run:    docker run -p 8000:8000 --env-file .env glmocr-server
# ============================================================

FROM python:3.12-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    fonts-liberation \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# --- App setup ---
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir git+https://github.com/huggingface/transformers.git

COPY . .

# --- Non-root user for security ---
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# --- Health check ---
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-c", "gunicorn.conf.py"]
