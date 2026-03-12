import os
import tempfile

from app.workers.celery_app import celery_app
from app.core.ocr_service import ocr_service


@celery_app.task(bind=True)
def run_ocr_task(self, content: bytes, original_name: str, suffix: str):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = ocr_service.process_file(tmp_path, original_name)
    finally:
        os.unlink(tmp_path)

    if result.error:
        raise Exception(result.error)

    return result.to_dict()
