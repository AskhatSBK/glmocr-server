from app.core.config import settings

bind = f"{settings.HOST}:{settings.PORT}"
workers = settings.WORKERS
worker_class = "uvicorn.workers.UvicornWorker"
accesslog = "-"
errorlog = "-"
loglevel = settings.LOG_LEVEL.lower()
