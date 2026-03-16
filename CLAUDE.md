# GLM-OCR Production Server

A production-ready FastAPI wrapper around the GLM-OCR SDK providing OCR services for PDFs, images, and Word documents.

## Architecture

```
app/
├── main.py              # FastAPI app, middleware registration
├── api/routes.py        # Endpoints: /parse, /parse/async, /jobs/{id}, /health
├── core/
│   ├── config.py        # Pydantic settings loaded from .env
│   ├── converter.py     # File → PIL Images (PDF via pypdfium2, Word via LibreOffice)
│   └── ocr_service.py   # OCR orchestration and response formatting
├── middleware/
│   ├── auth.py          # Bearer/X-API-Key validation
│   └── rate_limit.py    # In-memory sliding-window rate limiter
└── workers/
    ├── celery_app.py    # Celery + Redis configuration
    └── tasks.py         # Async OCR Celery task
docker/
├── Dockerfile           # Python 3.12-slim + LibreOffice + non-root user
└── docker-compose.yml   # vLLM model + Redis + API + Celery worker
```

## Tech Stack

- **Python 3.12**, FastAPI, Uvicorn, Gunicorn
- **glmocr** SDK for OCR
- **pypdfium2** for PDF rendering, **LibreOffice headless** for DOCX → PDF
- **Celery + Redis** for async task queue (optional)
- OCR backends: **vLLM**, **SGLang**, or **Zhipu MaaS** (API-based, no GPU)

## Development Setup

```bash
# System dependency
sudo apt install libreoffice

# Python dependencies
pip install -r requirements.txt
pip install git+https://github.com/huggingface/transformers.git

# Configure environment
cp .env.example .env
# Edit .env — set OCR_API_HOST/PORT or OCR_API_KEY for MaaS

# Run dev server
uvicorn app.main:app --reload --port 8000
```

## Running with Docker

```bash
cd docker
docker compose up -d
```

Starts: vLLM model server, Redis, FastAPI (port 8000), Celery worker.

## Key Commands

```bash
# Production server
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py

# vLLM model server
vllm serve zai-org/GLM-OCR --allowed-local-media-path / --port 8080

# Celery worker
celery -A app.workers.celery_app worker --loglevel=info
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Service info |
| GET | `/health` | No | Health check |
| POST | `/parse` | Optional | Synchronous OCR |
| POST | `/parse/async` | Optional | Async OCR (Celery) |
| GET | `/jobs/{job_id}` | Optional | Poll async job |

Auth is enabled only when `API_KEYS` is set in `.env`. Pass as `Authorization: Bearer <key>` or `X-API-Key: <key>`.

## Configuration (`.env`)

Key variables (see `.env.example` for full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Server bind |
| `WORKERS` | `1` | Gunicorn worker count |
| `API_KEYS` | (empty) | Comma-separated auth keys |
| `OCR_API_HOST` | `localhost` | OCR backend host |
| `OCR_API_PORT` | `8080` | OCR backend port |
| `OCR_API_KEY` | (empty) | For Zhipu MaaS |
| `MAX_FILE_SIZE_MB` | `50` | Upload size limit |
| `OUTPUT_FORMAT` | `both` | `json`, `markdown`, or `both` |
| `USE_TASK_QUEUE` | `false` | Enable Celery async |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |

## File Conversion Pipeline

```
Upload → Validation → converter.py
  .jpg/.png  → PIL Image (direct)
  .pdf       → pypdfium2 → PIL Images (one per page)
  .doc/.docx → LibreOffice → PDF → pypdfium2 → PIL Images
→ OCR Service → JSON response
```

## Supported File Types

PDF, JPG, JPEG, PNG, DOC, DOCX (max 50 MB by default)
