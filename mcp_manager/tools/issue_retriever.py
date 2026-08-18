import logging
from typing import Any

from crewai.tools import tool

from mcp_manager.utils import mcp_tool

logger = logging.getLogger(__name__)

_VALID_STATES = {"OPEN", "CLOSED"}


@tool("get_issue")
def get_issue(owner: str, repo: str, state: str = "open") -> list[dict[str, Any]]:
    """Fetch issues from a GitHub repository using the MCP list_issues tool."""
    try:
        normalized_state = str(state).upper()
        if normalized_state not in _VALID_STATES:
            normalized_state = "OPEN"

        result = mcp_tool(
            "list_issues",
            {
                "owner": owner,
                "repo": repo,
                "state": normalized_state,
                "perPage": 5,
            },
            toolsets="issues",
            read_only=True,  # issue_write's union-typed schema breaks mcpcurl flag parsing
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("issues", [])
        return []
    except Exception as exc:
        logger.error("get_issue failed for %s/%s: %s", owner, repo, exc)
        return []