"""Start analysis jobs — eager thread (local) or Redis list (prod)."""

from __future__ import annotations

import logging
import threading

from app.config import get_settings
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

QUEUE_KEY = "hover:jobs"


def enqueue_job(job_id: str) -> None:
    settings = get_settings()
    if settings.worker_eager:
        t = threading.Thread(target=run_pipeline, args=(job_id,), daemon=True)
        t.start()
        return

    try:
        import redis

        r = redis.from_url(settings.redis_url)
        r.lpush(QUEUE_KEY, job_id)
    except Exception as exc:
        logger.warning("redis enqueue failed (%s) — falling back to thread", exc)
        t = threading.Thread(target=run_pipeline, args=(job_id,), daemon=True)
        t.start()


def worker_loop() -> None:
    """Long-running Redis worker process."""
    import redis
    from app.config import get_settings

    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    logger.info("worker listening on %s", QUEUE_KEY)
    while True:
        item = r.brpop(QUEUE_KEY, timeout=0)
        if not item:
            continue
        _, job_id = item
        if isinstance(job_id, bytes):
            job_id = job_id.decode()
        run_pipeline(job_id)
