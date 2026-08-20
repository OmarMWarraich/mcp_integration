import logging
from typing import Any

from celery import shared_task

from ..crews.crew import build_crew

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def run_crew_task(self, owner: str, repo: str) -> dict[str, Any]:
    """Run the GitHub analysis crew asynchronously for a given repository.

    The task is idempotent: repeated runs for the same owner/repo simply
    re-execute the crew and return a fresh result. Errors are retried up to
    three times with exponential backoff.
    """
    logger.info("Starting crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)

    crew = build_crew(owner=owner, repo=repo)
    result = crew.kickoff()

    logger.info("Finished crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)

    return {
        "task_id": self.request.id,
        "owner": owner,
        "repo": repo,
        "status": "SUCCESS",
        "result": str(result),
    }
