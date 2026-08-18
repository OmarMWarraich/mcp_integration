import json

from crewai.tools import tool

from ..utils import get_repository_tree


@tool("get_repo_files")
def get_repo_files(owner: str, repo: str, path: str = ".") -> str:
    """List files and folders at a given path in a GitHub repository."""
    try:
        result = get_repository_tree(owner, repo, path)
    except Exception as exc:
        return f"Error retrieving repository structure: {exc}"

    return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)