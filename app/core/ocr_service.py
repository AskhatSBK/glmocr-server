"""
OCR service — thin wrapper around the GLM-OCR SDK.

Responsibilities:
  - Accept a file path
  - Convert to images via converter.py
  - Save images to a temp dir so GlmOcr.parse() can consume them
  - Return structured result
"""

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from app.core.config import settings
from app.core.converter import file_to_images

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OCRResult:
    filename: str
    page_count: int
    markdown: Optional[str]
    json_result: Optional[List[Any]]
    processing_time_seconds: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "page_count": self.page_count,
            "markdown": self.markdown,
            "json_result": self.json_result,
            "processing_time_seconds": round(self.processing_time_seconds, 3),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class OCRService:
    """
    Singleton-friendly OCR service.  GlmOcr is initialised once and reused
    across requests to avoid per-request model loading overhead.
    """

    def __init__(self) -> None:
        self._parser = None

    def _get_parser(self):
        """Lazy-initialise GlmOcr (imports are slow at module load time)."""
        if self._parser is None:
            try:
                import os
                from glmocr import GlmOcr
                # SDK reads selfhosted model name only from this env var
                os.environ.setdefault("GLMOCR_OCR_MODEL", settings.OCR_MODEL)
                self._parser = GlmOcr(
                    mode=settings.OCR_MODE,
                    ocr_api_host=settings.OCR_API_HOST,
                    ocr_api_port=settings.OCR_API_PORT,
                    api_key=settings.OCR_API_KEY or None,
                    enable_layout=settings.OCR_ENABLE_LAYOUT,
                    timeout=settings.OCR_REQUEST_TIMEOUT,
                )
                logger.info("GlmOcr parser initialised successfully.")
            except Exception as exc:
                logger.error("Failed to initialise GlmOcr: %s", exc)
                raise RuntimeError(f"GLM-OCR initialisation error: {exc}") from exc
        return self._parser

    # ------------------------------------------------------------------

    def process_file(self, file_path: str, original_filename: str) -> OCRResult:
        """
        Full pipeline: file → images → OCR → result.
        This is a synchronous call; wrap in asyncio.to_thread() for async contexts.
        """
        start = time.perf_counter()
        images: List[Image.Image] = []

        try:
            # 1. Convert file to images
            logger.info("Converting file: %s", original_filename)
            images = file_to_images(file_path)
            page_count = len(images)
            logger.info("Got %d page(s) from %s", page_count, original_filename)

            # 2. Save images to temp dir for GlmOcr
            with tempfile.TemporaryDirectory() as img_dir:
                img_paths = _save_images(images, img_dir)

                # 3. Run OCR
                parser = self._get_parser()
                # GlmOcr.parse() treats a list as pages of a single document
                raw_result = parser.parse(img_paths)

            elapsed = time.perf_counter() - start

            # 4. Extract outputs — parse() returns a list when given a list
            results = raw_result if isinstance(raw_result, list) else [raw_result]
            md_parts = [r.markdown_result for r in results if getattr(r, "markdown_result", None)]
            json_parts = [r.json_result for r in results if getattr(r, "json_result", None)]
            markdown = "\n\n".join(md_parts) if md_parts else None
            json_result = json_parts if json_parts else None

            return OCRResult(
                filename=original_filename,
                page_count=page_count,
                markdown=markdown,
                json_result=json_result,
                processing_time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.exception("OCR failed for %s: %s", original_filename, exc)
            return OCRResult(
                filename=original_filename,
                page_count=len(images),
                markdown=None,
                json_result=None,
                processing_time_seconds=elapsed,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_images(images: List[Image.Image], directory: str) -> List[str]:
    """Save PIL images to directory as lossless PNGs and return sorted path list."""
    paths = []
    for i, img in enumerate(images):
        p = os.path.join(directory, f"page_{i:04d}.png")
        img.save(p, format="PNG")
        paths.append(p)
    return paths


# Module-level singleton
ocr_service = OCRService()
