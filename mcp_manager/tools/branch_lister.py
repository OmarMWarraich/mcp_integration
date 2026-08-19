import logging
from typing import Any

from crewai.tools import tool

from mcp_manager.utils import mcp_tool

logger = logging.getLogger(__name__)

@tool("get_branches")
def get_branches(owner: str, repo: str) -> list[dict[str, Any]]:
    """Fetch branches from a GitHub repository using the MCP list_branches tool."""
    try:
        result = mcp_tool(
            "list_branches",
            {
                "owner": owner,
                "repo": repo,
            },
            toolsets="repos",
            read_only=True,
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("branches", [])
        return []
    except Exception as exc:
        logger.error("get_branches failed for %s/%s: %s", owner, repo, exc)
        return []