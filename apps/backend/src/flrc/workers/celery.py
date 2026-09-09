from celery import Celery

from flrc.config import settings

celery_app = Celery(
    "flrc",
    broker=settings.redis_url,
    include=["flrc.workers.tasks.exports"],
)
celery_app.conf.update(
    # Pin the wire format instead of relying on the default: an accepted
    # pickle payload on the broker would be remote code execution in the
    # worker, and job payloads here are plain JSON anyway.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    result_backend=None,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 60 * 60},
)
