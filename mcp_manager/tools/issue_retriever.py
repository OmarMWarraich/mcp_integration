import json

from crewai.tools import tool

from mcp_manager.utils import get_repository_issues


@tool("get_issue")
def get_issue(owner: str, repo: str) -> str:
    """Fetch a list of open issues from a GitHub repository using the GitHub API."""
    try:
        result = get_repository_issues(owner, repo, state='open', per_page=5)
    except Exception as exc:
        return f"Error retrieving open issues: {exc}"

    return json.dumps(result, ensure_ascii=False) if isinstance(result, list) else str(result)