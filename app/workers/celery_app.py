from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "glmocr",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # --- Memory & resource safeguards ---
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    worker_max_memory_per_child=settings.CELERY_WORKER_MAX_MEMORY_KB,  # KB
    result_expires=settings.CELERY_RESULT_EXPIRES,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    # Reject tasks on worker shutdown instead of losing them
    worker_cancel_long_running_tasks_on_connection_loss=True,
    task_reject_on_worker_lost=True,
    task_acks_late=True,
)
