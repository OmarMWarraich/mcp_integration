import json
from crewai.tools import tool

from ..utils import mcp_tool


@tool("get_repo_files")
def get_repo_files(owner: str, repo: str, path: str = "/") -> list:
    """List the files and directories at a path in a GitHub repository."""
    print(f"Repo Structure Lister: Get files at {path} for {owner}/{repo}")

    result = mcp_tool("get_file_contents", {
        "owner": owner,
        "repo": repo,
        "path": path or "/",
    })
    if isinstance(result, dict):
        return [result]
    return result if isinstance(result, list) else []