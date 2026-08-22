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


def build_crew(owner: str, repo: str, output_dir: str = "generated_docs", process: Process = Process.sequential) -> Crew:
    """Assemble a CrewAI crew for the requested repository.

    The crew is stateless and built from scratch on every call, making it safe
    to dispatch multiple times (idempotent). `output_dir` isolates each run's
    markdown artifacts. Pass `process=Process.parallel` to run the four
    analysis tasks concurrently.
    """
    tasks = []
    tasks.extend(analyze_repo_structure_task(owner, repo, output_dir))
    tasks.extend(get_issue_tasks(owner, repo, output_dir))
    tasks.extend(list_pull_requests_tasks(owner, repo, output_dir))
    tasks.extend(list_branches_tasks(owner, repo, output_dir))

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
