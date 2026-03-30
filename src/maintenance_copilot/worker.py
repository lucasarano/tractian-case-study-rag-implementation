from __future__ import annotations

import logging
import time
from contextlib import ExitStack

from maintenance_copilot.api import build_container
from maintenance_copilot.config import get_settings

logger = logging.getLogger(__name__)


def run_worker() -> None:
    settings = get_settings()
    with ExitStack() as exit_stack:
        container = build_container(settings, exit_stack=exit_stack)
        logger.info("manual ingest worker started")
        while True:
            job = container.manual_job_repo.claim_next_pending()
            if job is None:
                time.sleep(settings.worker_poll_interval_seconds)
                continue
            logger.info("processing manual ingest job %s", job.job_id)
            result = container.manual_job_processor.process(job)
            logger.info(
                "manual ingest job %s finished with status %s",
                result.job_id,
                result.status.value,
            )


if __name__ == "__main__":
    run_worker()
