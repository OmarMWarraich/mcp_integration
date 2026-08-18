import logging
from typing import Any

from crewai.tools import tool

from mcp_manager.utils import mcp_tool

logger = logging.getLogger(__name__)


@tool("get_pull_requests")
def get_pull_requests(owner: str, repo: str, state: str = "open") -> list[dict[str, Any]]:
    """Fetch only open pull requests from a GitHub repository using the MCP list_pull_requests tool."""
    try:
        normalized_state = str(state).lower()
        if normalized_state not in {"open", "closed", "all"}:
            normalized_state = "open"

        result = mcp_tool(
            "list_pull_requests",
            {
                "owner": owner,
                "repo": repo,
                "state": normalized_state,
                "perPage": 5,
            },
            toolsets="pull_requests",
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []
    except Exception as exc:
        logger.error("Error retrieving pull requests for %s/%s: %s", owner, repo, exc)
        return []