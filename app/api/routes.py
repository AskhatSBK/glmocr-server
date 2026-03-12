"""
API routes.

POST /parse          — upload a file, get OCR result (sync)
POST /parse/async    — upload a file, get a job_id  (async via Celery, optional)
GET  /jobs/{job_id}  — poll async job status
GET  /health         — liveness + readiness probe
GET  /               — basic info
"""

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.ocr_service import ocr_service

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = set(settings.ALLOWED_EXTENSIONS)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",                                                    # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_upload(file: UploadFile) -> None:
    """Raise HTTPException for invalid files before reading content."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "unsupported_file_type",
                "detail": f"File type '{suffix}' is not allowed.",
                "allowed": list(ALLOWED_EXTENSIONS),
            },
        )
    # Content-type check (best-effort — clients can lie)
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        logger.warning(
            "Suspicious content-type '%s' for file '%s'",
            file.content_type, file.filename,
        )


async def _read_upload(file: UploadFile) -> bytes:
    """Read upload content, enforcing max file size."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 256)  # 256 KB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "file_too_large",
                    "detail": f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit.",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", tags=["Info"])
async def root():
    return {
        "service": "GLM-OCR Production API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", tags=["Health"])
async def health():
    """Liveness + basic readiness probe."""
    return {
        "status": "ok",
        "ocr_backend": f"{settings.OCR_API_SCHEME}://{settings.OCR_API_HOST}:{settings.OCR_API_PORT}",
        "supported_formats": settings.ALLOWED_EXTENSIONS,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
    }


@router.post("/parse", tags=["OCR"])
async def parse_file(
    file: UploadFile = File(..., description="File to OCR (.pdf, .jpg, .jpeg, .png, .doc, .docx)"),
):
    """
    Upload a document and receive the OCR result synchronously.

    - **file**: multipart file upload
    - Returns JSON with `markdown` and/or `json_result` depending on server config.
    """
    _validate_upload(file)
    content = await _read_upload(file)

    suffix = Path(file.filename or "file").suffix.lower()
    original_name = file.filename or f"upload{suffix}"

    # Write to a named temp file so converter can open it by path
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info(
            "Processing '%s' (%.2f MB) synchronously",
            original_name,
            len(content) / 1024 / 1024,
        )
        # Run blocking OCR in a thread so the event loop stays free
        result = await asyncio.to_thread(
            ocr_service.process_file, tmp_path, original_name
        )
    finally:
        os.unlink(tmp_path)

    if result.error:
        raise HTTPException(
            status_code=422,
            detail={"error": "ocr_failed", "detail": result.error},
        )

    return JSONResponse(content=result.to_dict())


@router.post("/parse/async", tags=["OCR"])
async def parse_file_async(
    file: UploadFile = File(...),
):
    """
    Submit a file for async OCR processing.
    Returns a `job_id` you can poll via GET /jobs/{job_id}.

    Requires `USE_TASK_QUEUE=true` and a running Celery worker + Redis.
    """
    if not settings.USE_TASK_QUEUE:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "task_queue_disabled",
                "detail": "Set USE_TASK_QUEUE=true and configure Redis to enable async processing.",
            },
        )

    _validate_upload(file)
    content = await _read_upload(file)
    suffix = Path(file.filename or "file").suffix.lower()
    original_name = file.filename or f"upload{suffix}"

    from app.workers.tasks import run_ocr_task  # only import when queue is enabled

    job_id = str(uuid.uuid4())
    run_ocr_task.apply_async(
        args=[content, original_name, suffix],
        task_id=job_id,
    )

    logger.info("Queued async OCR job %s for '%s'", job_id, original_name)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
    )


@router.get("/jobs/{job_id}", tags=["OCR"])
async def get_job(job_id: str):
    """Poll the status and result of an async OCR job."""
    if not settings.USE_TASK_QUEUE:
        raise HTTPException(status_code=501, detail="Task queue is disabled.")

    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app

    task = AsyncResult(job_id, app=celery_app)

    if task.state == "PENDING":
        return {"job_id": job_id, "status": "pending"}
    elif task.state == "STARTED":
        return {"job_id": job_id, "status": "processing"}
    elif task.state == "SUCCESS":
        return {"job_id": job_id, "status": "completed", "result": task.result}
    elif task.state == "FAILURE":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(task.result),
        }
    else:
        return {"job_id": job_id, "status": task.state.lower()}
