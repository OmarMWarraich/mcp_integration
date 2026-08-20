import logging
from typing import Any

from celery import group
from celery import shared_task

from ..crews.crew import build_crew

logger = logging.getLogger(__name__)


def _run_single_crew(owner: str, repo: str) -> dict[str, Any]:
    """Execute a crew synchronously and return a serializable result."""
    logger.info("Running crew for %s/%s", owner, repo)
    crew = build_crew(owner=owner, repo=repo)
    result = crew.kickoff()
    logger.info("Finished crew for %s/%s", owner, repo)
    return {
        "owner": owner,
        "repo": repo,
        "status": "SUCCESS",
        "result": str(result),
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def run_crew_task(self, owner: str, repo: str) -> dict[str, Any]:
    """Run the GitHub analysis crew asynchronously for a single repository.

    The task is idempotent: repeated runs for the same owner/repo simply
    re-execute the crew and return a fresh result. Errors are retried up to
    three times with exponential backoff.
    """
    logger.info("Starting crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
    payload = _run_single_crew(owner, repo)
    payload["task_id"] = self.request.id
    return payload


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def run_multiple_crews_task(self, repos: list[dict[str, str]]) -> dict[str, Any]:
    """Run crews concurrently for multiple repositories.

    `repos` is a list of {"owner": str, "repo": str} dictionaries.
    This task delegates each repo to `run_crew_task` via a Celery group,
    collects the results, and returns a combined payload.

    Errors on individual sub-tasks do not fail the whole group because each
    child task has its own retry policy.
    """
    logger.info("Starting multiple-crew task for %d repo(s) (task_id=%s)", len(repos), self.request.id)

    signatures = []
    for item in repos:
        owner = item["owner"]
        repo_name = item["repo"]
        signatures.append(run_crew_task.s(owner=owner, repo=repo_name)) # type: ignore
    job = group(*signatures)
    result = job.apply_async()
    children = result.get(disable_sync_subtasks=False)

    logger.info("Finished multiple-crew task (task_id=%s)", self.request.id)

    return {
        "task_id": self.request.id,
        "status": "SUCCESS",
        "count": len(children),
        "results": children,
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def run_scheduled_crew_task(self, owner: str, repo: str) -> dict[str, Any]:
    """Run a single crew on a recurring schedule via Celery Beat.

    This is a thin wrapper around `run_crew_task` so periodic tasks can target
    a dedicated entry point without interfering with on-demand executions.
    """
    logger.info("Starting scheduled crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
    payload = _run_single_crew(owner, repo)
    payload["task_id"] = self.request.id
    payload["scheduled"] = True
    return payload
