from __future__ import annotations

from crewai import Crew, Process

from ..agents.agents import (
    repo_structure_auditor,
    issue_analyst,
    pull_requests_fetcher_reporter,
    branches_fetcher_reporter,
)
from ..tasks.tasks import (
    analyze_repo_structure_task,
    get_issue_tasks,
    list_pull_requests_tasks,
    list_branches_tasks,
)


def build_crew(owner: str, repo: str, process: Process = Process.sequential) -> Crew:
    """Assemble a CrewAI crew for the requested repository.

    The crew is stateless and built from scratch on every call, making it safe
    to dispatch multiple times (idempotent). Pass `process=Process.parallel`
    to run the four analysis tasks concurrently.
    """
    tasks = []
    tasks.extend(analyze_repo_structure_task(owner, repo))
    tasks.extend(get_issue_tasks(owner, repo))
    tasks.extend(list_pull_requests_tasks(owner, repo))
    tasks.extend(list_branches_tasks(owner, repo))

    return Crew(
        agents=[
            repo_structure_auditor,
            issue_analyst,
            pull_requests_fetcher_reporter,
            branches_fetcher_reporter,
        ],
        tasks=tasks,
        process=process,
        verbose=True,
        cache=True,
    )
