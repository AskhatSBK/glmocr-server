# GLM-OCR Production Server

A production-ready FastAPI wrapper around the [GLM-OCR](https://github.com/zai-org/GLM-OCR) SDK, supporting file uploads for PDF, images, and Word documents.

## Supported formats

| Format | Extension | Conversion |
|--------|-----------|------------|
| Images | `.jpg`, `.jpeg`, `.png` | Direct |
| PDF | `.pdf` | `pypdfium2` (no system deps) |
| Word | `.docx`, `.doc` | LibreOffice headless → PDF → images |

---

## Quick start

### 1. Install system dependency (for Word support)

```bash
# Ubuntu / Debian
sudo apt install libreoffice

# macOS
brew install libreoffice
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
pip install git+https://github.com/huggingface/transformers.git
```

### 3. Start the GLM-OCR model server

**Option A — Zhipu MaaS (no GPU needed):**

Get an API key from https://open.bigmodel.cn and set `OCR_API_KEY` in `.env`.

**Option B — Self-host with vLLM:**

```bash
pip install -U vllm --extra-index-url https://wheels.vllm.ai/nightly
vllm serve zai-org/GLM-OCR --allowed-local-media-path / --port 8080
```

**Option C — Self-host with SGLang:**

```bash
python -m sglang.launch_server --model zai-org/GLM-OCR --port 8080
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — set OCR_API_HOST, API_KEYS, etc.
```

### 5. Run the server

**Development:**
```bash
uvicorn app.main:app --reload --port 8000
```

**Production:**
```bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py
```

---

## API

### `POST /parse` — Synchronous OCR

```bash
curl -X POST http://localhost:8000/parse \
  -H "Authorization: Bearer your-secret-key-1" \
  -F "file=@document.pdf"
```

**Response:**
```json
{
  "filename": "document.pdf",
  "page_count": 3,
  "markdown": "# Document Title\n\nBody...",
  "json_result": [[{ "index": 0, "label": "text", "content": "..." }]],
  "processing_time_seconds": 4.231,
  "error": null
}
```

### `POST /parse/async` — Async OCR (requires Redis)

```bash
curl -X POST http://localhost:8000/parse/async \
  -H "Authorization: Bearer your-key" \
  -F "file=@large_document.pdf"
# → { "job_id": "abc-123", "status": "queued" }
```

### `GET /jobs/{job_id}` — Poll async job

```bash
curl http://localhost:8000/jobs/abc-123 \
  -H "Authorization: Bearer your-key"
# → { "job_id": "abc-123", "status": "completed", "result": { ... } }
```

### `GET /health`

```bash
curl http://localhost:8000/health
```

---

## Docker deployment

```bash
cd docker
docker compose up -d
```

This starts:
- `glmocr-model` — vLLM serving `zai-org/GLM-OCR` on port 8080
- `glmocr-api` — FastAPI server on port 8000
- `redis` — Task queue backend
- `glmocr-worker` — Celery worker for async jobs

---

## Configuration reference

All settings are environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `WORKERS` | `4` | Gunicorn worker count |
| `API_KEYS` | _(empty)_ | Comma-separated keys; empty = auth disabled |
| `RATE_LIMIT_REQUESTS` | `60` | Max requests per window per IP |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `OCR_API_HOST` | `localhost` | GLM-OCR model server host |
| `OCR_API_PORT` | `8080` | GLM-OCR model server port |
| `OCR_API_KEY` | _(empty)_ | API key for MaaS mode |
| `OUTPUT_FORMAT` | `both` | `json`, `markdown`, or `both` |
| `USE_TASK_QUEUE` | `false` | Enable async Celery jobs |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

---

## Architecture

```
Client (multipart upload)
        │
        ▼
  FastAPI (Uvicorn + Gunicorn)
  ├── APIKeyMiddleware      ← auth
  ├── RateLimitMiddleware   ← per-IP sliding window
  └── POST /parse
            │
            ├── Validate extension + size
            ├── Write to NamedTempFile
            │
            ▼
      converter.py
      ├── .jpg/.png  → PIL Image
      ├── .pdf       → pypdfium2 → PIL Images
      └── .doc/.docx → LibreOffice → PDF → pypdfium2 → PIL Images
            │
            ▼
      ocr_service.py
      ├── Save images to temp dir
      └── GlmOcr.parse(image_paths)
                │
                ▼
          vLLM / SGLang / MaaS
          (zai-org/GLM-OCR model)
                │
                ▼
      OCRResult { markdown, json_result }
            │
            ▼
        JSON response
```

For async mode, the upload is handed to Celery + Redis instead of being processed inline.
