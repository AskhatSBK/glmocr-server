"""
OCR service — RunPod serverless backend.

Drop-in replacement for ocr_service.py that routes all requests through
the RunPod serverless endpoint instead of a local vLLM/SGLang instance.

Same public interface:
  ocr_service.process_file(file_path, original_filename) -> OCRResult
"""

import logging
import time
from typing import Any, Dict, List, Optional

from PIL import Image

from app.core.config import settings
from app.core.converter import file_to_images
from app.core.runpod_client import RunPodClient

logger = logging.getLogger(__name__)


# Re-use the same result dataclass shape so routes.py needs no changes.
from dataclasses import dataclass, field


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


class RunPodOCRService:
    """OCR service backed by RunPod serverless."""

    def __init__(self) -> None:
        self._client = RunPodClient(
            endpoint_url=settings.RUNPOD_ENDPOINT_URL,
            api_key=settings.RUNPOD_API_KEY,
            timeout=settings.RUNPOD_TIMEOUT,
        )
        logger.info("RunPodOCRService ready → %s", settings.RUNPOD_ENDPOINT_URL)

    def process_file(self, file_path: str, original_filename: str) -> OCRResult:
        """Full pipeline: file → images → RunPod OCR → result."""
        start = time.perf_counter()
        images: List[Image.Image] = []

        try:
            logger.info("Converting file: %s", original_filename)
            images = file_to_images(file_path)
            page_count = len(images)
            logger.info("Got %d page(s) from %s", page_count, original_filename)

            output = self._client.process_images(images, output_format=settings.OUTPUT_FORMAT)
            elapsed = time.perf_counter() - start

            return OCRResult(
                filename=original_filename,
                page_count=page_count,
                markdown=output.get("markdown"),
                json_result=output.get("json_result"),
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


# Module-level singleton
ocr_service = RunPodOCRService()
