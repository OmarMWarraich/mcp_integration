import logging
from typing import Any

from crewai.tools import tool

from mcp_manager.utils import get_repository_pull_requests

logger = logging.getLogger(__name__)


@tool("get_pull_requests")
def get_pull_requests(owner: str, repo: str) -> list[dict[str, Any]]:
    """
    Fetch a list of open pull requests from a GitHub repository using the GitHub API.
    """
    try:
        return get_repository_pull_requests(owner, repo, state="open", per_page=5)
    except Exception as exc:
        logger.error("Error retrieving open pull requests for %s/%s: %s", owner, repo, exc)
        return []