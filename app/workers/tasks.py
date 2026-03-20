import logging
import os

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.workers.celery_app import celery_app
from app.core.ocr_service import ocr_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def run_ocr_task(self: Task, file_path: str, original_name: str):
    """
    Process a file that has already been saved to disk.

    The caller (routes.py) writes the upload to a persistent temp file
    and passes its path here, so large files never travel through Redis.
    """
    try:
        result = ocr_service.process_file(file_path, original_name)
    except SoftTimeLimitExceeded:
        logger.error("OCR task %s timed out for '%s'", self.request.id, original_name)
        raise
    finally:
        # Always clean up the temp file
        try:
            os.unlink(file_path)
        except FileNotFoundError:
            pass

    if result.error:
        raise Exception(result.error)

    return result.to_dict()
