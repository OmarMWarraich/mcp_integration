from __future__ import annotations

import logging
import time
from typing import Any

from celery import group, shared_task

from ..crews.crew import build_crew

logger = logging.getLogger(__name__)


def _serialize_crew_result(result: Any) -> dict[str, Any]:
    """Convert a CrewAI result into a structured, JSON-serializable payload."""
    try:
        raw = str(result)
    except Exception as exc:  # pragma: no cover
        raw = f"<unserializable result: {exc}>"

    return {
        "raw_output": raw,
        "serialized_at": time.time(),
    }


def _run_single_crew(owner: str, repo: str) -> dict[str, Any]:
    """Execute a crew synchronously and return a serializable result.

    This helper is intentionally stateless: it builds a fresh crew every time
    so repeated calls for the same owner/repo are idempotent.
    """
    logger.info("Running crew for %s/%s", owner, repo)
    crew = build_crew(owner=owner, repo=repo)
    result = crew.kickoff()
    logger.info("Finished crew for %s/%s", owner, repo)
    return {
        "owner": owner,
        "repo": repo,
        "status": "SUCCESS",
        **_serialize_crew_result(result),
    }


def _format_error_payload(task_id: str | None, owner: str, repo: str, exc: Exception) -> dict[str, Any]:
    """Build a clean, structured error payload for a failed crew run."""
    logger.exception("Crew task failed for %s/%s (task_id=%s)", owner, repo, task_id)
    return {
        "task_id": task_id,
        "owner": owner,
        "repo": repo,
        "status": "FAILURE",
        "error": type(exc).__name__,
        "message": str(exc),
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

    The task is idempotent: repeated runs for the same owner/repo build a fresh
    crew and return a fresh result. Errors are retried up to three times with
    exponential backoff.
    """
    logger.info("Starting crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
    try:
        payload = _run_single_crew(owner, repo)
    except Exception as exc:
        payload = _format_error_payload(self.request.id, owner, repo, exc)
        raise self.retry(exc=exc) from exc

    payload["task_id"] = self.request.id
    logger.info("Completed crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
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

    Each child task has its own retry policy, so an error in one repo does not
    fail the whole group.
    """
    logger.info("Starting multiple-crew task for %d repo(s) (task_id=%s)", len(repos), self.request.id)

    signatures = []
    for item in repos:
        owner = str(item.get("owner", "")).strip()
        repo_name = str(item.get("repo", "")).strip()
        if not owner or not repo_name:
            raise ValueError(f"Invalid repo entry: {item}")
        signatures.append(run_crew_task.s(owner=owner, repo=repo_name))  # type: ignore[arg-type]

    job = group(*signatures)
    result = job.apply_async()

    # NOTE: Joining a group inside a task can block a worker process; consider returning
    # child task IDs instead if this becomes a bottleneck.
    from celery.result import allow_join_result

    with allow_join_result():
        children = result.get(disable_sync_subtasks=False, propagate=False)

    normalized_children: list[dict[str, Any]] = []
    for child, repo in zip(children, repos):
        if isinstance(child, Exception):
            normalized_children.append(
                _format_error_payload(None, str(repo.get("owner", "")), str(repo.get("repo", "")), child)
            )
        elif isinstance(child, dict):
            normalized_children.append(child)
        else:
            normalized_children.append({"status": "SUCCESS", **_serialize_crew_result(child)})

    logger.info("Finished multiple-crew task (task_id=%s)", self.request.id)

    return {
        "task_id": self.request.id,
        "status": "SUCCESS",
        "count": len(normalized_children),
        "results": normalized_children,
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

    This is a thin wrapper around `_run_single_crew` so periodic tasks can target
    a dedicated entry point without interfering with on-demand executions.
    """
    logger.info("Starting scheduled crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
    try:
        payload = _run_single_crew(owner, repo)
    except Exception as exc:
        payload = _format_error_payload(self.request.id, owner, repo, exc)
        raise self.retry(exc=exc) from exc

    payload["task_id"] = self.request.id
    payload["scheduled"] = True
    logger.info("Completed scheduled crew task for %s/%s (task_id=%s)", owner, repo, self.request.id)
    return payload


@shared_task
def validate_crew_payload(repos: list[dict[str, str]]) -> dict[str, Any]:
    """Lightweight validation helper to sanity-check a batch payload.

    Returns a JSON-friendly report of the repos that will be processed. This is
    useful for API pre-flight checks before dispatching `run_multiple_crews_task`.
    """
    validated = []
    for item in repos:
        owner = item.get("owner", "").strip()
        repo_name = item.get("repo", "").strip()
        if not owner or not repo_name:
            raise ValueError(f"Invalid repo entry: {item}")
        validated.append({"owner": owner, "repo": repo_name})

    return {"valid": True, "count": len(validated), "repos": validated}
