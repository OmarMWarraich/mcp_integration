"""Documentation generation service: URL parsing, crew orchestration, markdown
combining, HTML conversion/sanitization, and persistence."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from urllib.parse import urlparse

import markdown as md
import nh3
from django.conf import settings

logger = logging.getLogger(__name__)

OUTPUT_FILENAMES = [
    "repo_structure.md",
    "report_issues.md",
    "pull_requests.md",
    "branches.md",
]


def extract_owner_repo(repo_url: str) -> tuple[str, str]:
    """Parse a GitHub repository URL into (owner, repo). Raises ValueError."""
    url = repo_url.strip()
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.netloc.lower() not in ("github.com", "www.github.com"):
        raise ValueError("Invalid GitHub repository URL format.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Invalid GitHub repository URL format.")
    owner, repo = parts[0], parts[1]
    return owner, repo.removesuffix(".git")


def run_output_dir(run_id: str) -> Path:
    """Per-run output directory so concurrent crews never clobber each other."""
    return Path(settings.BASE_DIR) / "generated_docs" / run_id


def combine_markdown_files(output_dir: Path, owner: str, repo: str) -> str:
    """Combine the per-run markdown files into a single markdown document."""
    combined = f"# Summary for {owner}/{repo}\n"
    for filename in OUTPUT_FILENAMES:
        path = output_dir / filename
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            logger.warning("Missing crew output file: %s", path)
            continue
        # Strip a ```markdown fence the LLM sometimes wraps output in
        if lines and lines[0].strip() == "```markdown" and lines[-1].strip() == "```":
            lines = lines[1:-1]
        combined += "\n\n---\n\n" + "\n".join(lines).strip()
    return combined.strip()


def convert_markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML and sanitize it (LLM output is untrusted)."""
    html = md.markdown(markdown_text, extensions=["extra"])
    return nh3.clean(html)


def generate_documentation(owner: str, repo: str, repo_url: str = "", run_id: str | None = None):
    """Run the analysis crew for a repository and persist the sanitized HTML report.

    Uses a per-run output directory keyed by `run_id` (defaults to a fresh UUID),
    making concurrent runs safe. Returns the created GeneratedDocument.
    """
    # Deferred imports: this module is loaded from celery.py before Django apps
    # are ready, and crewai's import chain is heavy.
    from ..crews.crew import build_crew
    from ..models import GeneratedDocument, GitHubRepository

    run_id = run_id or uuid.uuid4().hex
    output_dir = run_output_dir(run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running crew for %s/%s (run_id=%s)", owner, repo, run_id)
    crew = build_crew(owner=owner, repo=repo, output_dir=str(output_dir))
    crew.kickoff()

    combined = combine_markdown_files(output_dir, owner, repo)
    (output_dir / "summary.md").write_text(combined, encoding="utf-8")
    html_content = convert_markdown_to_html(combined)

    repository, _ = GitHubRepository.objects.get_or_create(
        owner=owner,
        name=repo,
        defaults={"url": repo_url or f"https://github.com/{owner}/{repo}"},
    )
    document = GeneratedDocument.objects.create(
        repository=repository,
        content=html_content,
        format="html",
        task_id=run_id,
    )
    logger.info("Persisted document %s for %s/%s", document.pk, owner, repo)
    return document