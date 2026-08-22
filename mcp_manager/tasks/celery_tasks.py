from __future__ import annotations

import logging
import time
from typing import Any

from celery import group, shared_task

from ..services.documentation import generate_documentation

logger = logging.getLogger(__name__)


def _get_or_create_run(task_id: str, owner: str, repo: str, status: str = "PENDING") -> Any:
    """Deferred import helper: returns a CrewRun row for this task."""
    from ..models import CrewRun, GitHubRepository

    repository, _ = GitHubRepository.objects.get_or_create(
        owner=owner,
        name=repo,
        defaults={"url": f"https://github.com/{owner}/{repo}"},
    )
    run, _ = CrewRun.objects.get_or_create(
        task_id=task_id,
        defaults={"repository": repository, "status": status},
    )
    return run


def _run_single_crew(owner: str, repo: str, run_id: str | None = None) -> dict[str, Any]:
    """Execute a crew synchronously, persist the report, and return a serializable result.

    This helper is intentionally stateless: it builds a fresh crew every time
    so repeated calls for the same owner/repo are idempotent. Output files are
    isolated per run, so concurrent runs never clobber each other.
    """
    logger.info("Running crew for %s/%s", owner, repo)
    document = generate_documentation(owner=owner, repo=repo, run_id=run_id)
    logger.info("Finished crew for %s/%s (document_id=%s)", owner, repo, document.pk)
    return {
        "owner": owner,
        "repo": repo,
        "status": "SUCCESS",
        "document_id": document.pk,
        "serialized_at": time.time(),
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
    task_id = self.request.id
    logger.info("Starting crew task for %s/%s (task_id=%s)", owner, repo, task_id)
    run = _get_or_create_run(task_id, owner, repo, status="PENDING")
    try:
        payload = _run_single_crew(owner, repo, run_id=task_id)
        run.status = "SUCCESS"
    except Exception as exc:
        run.status = "FAILURE"
        run.error_message = str(exc)
        run.save()
        raise
    finally:
        run.save()

    payload["task_id"] = task_id
    logger.info("Completed crew task for %s/%s (task_id=%s)", owner, repo, task_id)
    return payload


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def run_multiple_crews_task(self, repos: list[dict[str, str]]) -> dict[str, Any]:
    """Dispatch crews concurrently for multiple repositories.

    `repos` is a list of {"owner": str, "repo": str} dictionaries. Each repo is
    delegated to `run_crew_task` via a Celery group and the child task IDs are
    returned immediately — joining a group inside a task can deadlock workers
    (guaranteed with the solo pool), so callers poll each child via
    `/crew-status/<child_task_id>/`.

    Each child task has its own retry policy, so an error in one repo does not
    affect the others.
    """
    logger.info("Starting multiple-crew task for %d repo(s) (task_id=%s)", len(repos), self.request.id)

    signatures = []
    normalized: list[dict[str, str]] = []
    for item in repos:
        owner = str(item.get("owner", "")).strip()
        repo_name = str(item.get("repo", "")).strip()
        if not owner or not repo_name:
            raise ValueError(f"Invalid repo entry: {item}")
        normalized.append({"owner": owner, "repo": repo_name})
        signatures.append(run_crew_task.s(owner=owner, repo=repo_name))  # type: ignore[arg-type]

    result = group(*signatures).apply_async()

    children = [
        {"task_id": child.id, **repo}
        for child, repo in zip(result.children or [], normalized)
    ]

    logger.info("Dispatched %d child crew task(s) (task_id=%s)", len(children), self.request.id)

    return {
        "task_id": self.request.id,
        "status": "SUCCESS",
        "count": len(children),
        "children": children,
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
    task_id = self.request.id
    logger.info("Starting scheduled crew task for %s/%s (task_id=%s)", owner, repo, task_id)
    run = _get_or_create_run(task_id, owner, repo, status="PENDING")
    try:
        payload = _run_single_crew(owner, repo, run_id=task_id)
        run.status = "SUCCESS"
    except Exception as exc:
        run.status = "FAILURE"
        run.error_message = str(exc)
        run.save()
        raise
    finally:
        run.save()

    payload["task_id"] = task_id
    payload["scheduled"] = True
    logger.info("Completed scheduled crew task for %s/%s (task_id=%s)", owner, repo, task_id)
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
