"""Parametrized factory for GitHub MCP tool wrappers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from crewai.tools import tool

from mcp_manager.utils import mcp_tool

logger = logging.getLogger(__name__)


def make_mcp_tool(
    name: str,
    mcp_tool_name: str,
    toolsets: str,
    description: str,
    *,
    read_only: bool = False,
    extra_args: dict[str, Any] | None = None,
) -> Callable[..., list[dict[str, Any]]]:
    """Create a CrewAI tool that calls a GitHub MCP tool via mcpcurl."""
    extra = extra_args or {}

    def _impl(owner: str, repo: str, **kwargs: Any) -> list[dict[str, Any]]:
        arguments = {"owner": owner, "repo": repo, **extra, **kwargs}
        try:
            result = mcp_tool(
                mcp_tool_name,
                arguments,
                toolsets=toolsets,
                read_only=read_only,
            )
        except Exception as exc:
            logger.error("%s failed for %s/%s: %s", name, owner, repo, exc)
            return []

        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return (
                result.get("items", [])
                or result.get("issues", [])
                or result.get("branches", [])
                or [result]
            )
        return []

    _impl.__doc__ = description
    return tool(name)(_impl)


get_repo_files = make_mcp_tool(
    "get_repo_files",
    "get_file_contents",
    "repos",
    "List the files and directories at a path in a GitHub repository.",
)

get_issue = make_mcp_tool(
    "get_issue",
    "list_issues",
    "issues",
    "Fetch open issues from a GitHub repository using the MCP list_issues tool.",
    read_only=True,
    extra_args={"state": "OPEN", "perPage": 5},
)

get_pull_requests = make_mcp_tool(
    "get_pull_requests",
    "list_pull_requests",
    "pull_requests",
    "Fetch recent pull requests from a GitHub repository using list_pull_requests.",
    extra_args={"state": "open", "perPage": 5},
)

get_branches = make_mcp_tool(
    "get_branches",
    "list_branches",
    "repos",
    "Fetch branches from a GitHub repository using list_branches.",
    read_only=True,
)