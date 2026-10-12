import os
from celery import Celery
from celery.signals import worker_process_init

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "cognai_worker",
    broker=redis_url,
    backend=redis_url,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_concurrency=2
)

@worker_process_init.connect
def init_worker_process(**kwargs):
    """
    Ensure each forked Celery worker child process disposes any inherited
    database engines and connections so they never cross fork boundaries.
    """
    try:
        from app.db.database import engine
        engine.sync_engine.dispose()
    except Exception:
        pass
