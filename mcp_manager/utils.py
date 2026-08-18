
import json
import os
import subprocess
from typing import Any
import requests

from django.conf import settings


def _build_mcpcurl_args(arguments: dict[str, Any]) -> list[str]:
    """Convert a dict of arguments into CLI flags expected by mcpcurl tool commands."""
    flags: list[str] = []
    for key, value in arguments.items():
        if value is None:
            continue

        flag = f"--{key}"
        if isinstance(value, bool):
            flags.extend([flag, str(value).lower()])
        elif isinstance(value, (list, tuple, set)):
            if not value:
                continue
            flags.extend([flag, json.dumps(list(value))])
        elif isinstance(value, (dict, list)):
            flags.extend([flag, json.dumps(value)])
        else:
            flags.extend([flag, str(value)])
    return flags


def mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    toolsets: str = "repos",
) -> dict[str, Any] | list[dict[str, Any]] | str | None:
    """
    Execute an MCP tool via mcpcurl using the generated CLI command for the tool.

    toolsets must stay minimal: the 'issues' toolset schema contains a union-typed
    property that breaks mcpcurl's dynamic command generation, disabling ALL tool
    subcommands (symptom: "unknown flag: --owner").

    Example:
        mcp_tool("get_file_contents", {"owner": "octo", "repo": "hello", "path": "/"})
        -> ./mcpcurl --stdio-server-cmd ... tools get_file_contents --owner octo --repo hello --path /
    """
    mcpcurl_path = os.path.join(os.getcwd(), "mcpcurl")
    github_mcp_server_path = os.getenv(
        "GITHUB_MCP_SERVER",
        getattr(settings, "GITHUB_MCP_SERVER", None),
    )

    if not github_mcp_server_path:
        print("Error: GITHUB_MCP_SERVER environment variable is not set.")
        return None

    base_command = [
        mcpcurl_path,
        "--stdio-server-cmd",
        f"{github_mcp_server_path} --toolsets {toolsets} stdio",
        "tools",
        tool_name,
        * _build_mcpcurl_args(arguments),
    ]

    env = {
        "GITHUB_PERSONAL_ACCESS_TOKEN": getattr(settings, "GITHUB_PERSONAL_ACCESS_TOKEN", ""),
    }

    print(f"mcp_tool executing command: {base_command}")

    try:
        process = subprocess.Popen(
            base_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        stdout, stderr = process.communicate(timeout=20)

        if stderr:
            print(f"mcpcurl stderr: {stderr}")

        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                print(f"mcpcurl stdout is not valid JSON: {stdout}")
                return stdout.strip()

        return None

    except FileNotFoundError:
        print(f"Error: mcpcurl not found at {mcpcurl_path}")
        return None
    except subprocess.TimeoutExpired:
        print("Error: Timeout communicating with mcpcurl.")
        return None
    except Exception as exc:
        print(f"An unexpected error occurred while running mcpcurl: {exc}")
        return None


# def get_repository_tree(owner: str, repo: str, path: str = ".") -> list[dict]:
#     """
#     Return a GitHub repository tree for the requested folder using the GitHub API,
#     which is more reliable than the current mcpcurl wrapper.
#     """
#     token = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')
#     try:
#         token = token or getattr(settings, 'GITHUB_PERSONAL_ACCESS_TOKEN', None)
#     except Exception:
#         pass

#     headers = {'Accept': 'application/vnd.github+json'}
#     if token:
#         headers['Authorization'] = f'Bearer {token}'

#     url = f'https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1'
#     response = requests.get(url, headers=headers, timeout=30)
#     response.raise_for_status()
#     tree = response.json().get('tree', [])

#     normalized_path = path.strip('/') if path and path != '.' else ''
#     items: list[dict] = []
#     for entry in tree:
#         entry_path = entry.get('path', '')
#         if not entry_path:
#             continue

#         if normalized_path:
#             if entry_path == normalized_path:
#                 continue
#             if not entry_path.startswith(f'{normalized_path}/'):
#                 continue
#             rel_path = entry_path[len(normalized_path) + 1:]
#         else:
#             rel_path = entry_path

#         if '/' in rel_path:
#             continue

#         item = dict(entry)
#         item['relative_path'] = rel_path
#         item['html_url'] = f'https://github.com/{owner}/{repo}/blob/main/{entry_path}' if entry.get('type') == 'blob' else f'https://github.com/{owner}/{repo}/tree/main/{entry_path}'
#         items.append(item)

#     return items


def get_repository_issues(owner: str, repo: str, state: str = 'open', per_page: int = 5) -> list[dict]:
    """Return open issues for a repo using the GitHub REST API."""
    token = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')
    try:
        token = token or getattr(settings, 'GITHUB_PERSONAL_ACCESS_TOKEN', None)
    except Exception:
        pass

    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    url = f'https://api.github.com/repos/{owner}/{repo}/issues'
    params = {'state': state, 'per_page': per_page, 'page': 1}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    issues = response.json()
    return [
        {
            'title': item.get('title'),
            'html_url': item.get('html_url'),
            'state': item.get('state'),
            'number': item.get('number'),
            'user': item.get('user', {}).get('login') if isinstance(item.get('user'), dict) else None,
            'created_at': item.get('created_at'),
        }
        for item in issues
        if item.get('pull_request') is None
    ]

def get_repository_pull_requests(owner: str, repo: str, state: str = "open", per_page: int = 5) -> list[dict[str, Any]]:
    """Return pull requests for a repo using the GitHub REST API."""
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    try:
        token = token or getattr(settings, "GITHUB_PERSONAL_ACCESS_TOKEN", None)
    except Exception:
        token = None

    if not token:
        return []

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    params = {"state": state, "per_page": per_page}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        items = response.json() or []
    except requests.RequestException:
        return []

    return [
        {
            "title": item.get("title"),
            "html_url": item.get("html_url"),
            "state": item.get("state"),
            "number": item.get("number"),
            "user": item.get("user", {}).get("login") if isinstance(item.get("user"), dict) else None,
            "created_at": item.get("created_at"),
        }
        for item in items
    ]    
# def mcp_tool(command_args: list[str]) -> dict | list | str | None:
#     """
#     Executes mcpcurl with the given command arguments and returns the JSON response.
#     """
#     ...