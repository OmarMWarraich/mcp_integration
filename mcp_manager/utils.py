
import json
import os
import subprocess
import sys
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
    read_only: bool = False,
) -> Any:
    """
    Invoke a GitHub MCP tool via mcpcurl.

    read_only=True passes --read-only to github-mcp-server, excluding write tools
    like 'issue_write', whose union-typed schema breaks mcpcurl's dynamic command
    generation, disabling ALL tool subcommands (symptom: "unknown flag: --owner").

    Example:
        mcp_tool("get_file_contents", {"owner": "octo", "repo": "hello", "path": "/"})
        -> ./mcpcurl --stdio-server-cmd ... tools get_file_contents --owner octo --repo hello --path /
    """
    mcpcurl_name = "mcpcurl.exe" if sys.platform == "win32" else "mcpcurl"
    mcpcurl_path = os.path.join(os.getcwd(), mcpcurl_name)
    github_mcp_server_path = os.getenv(
        "GITHUB_MCP_SERVER",
        getattr(settings, "GITHUB_MCP_SERVER", None),
    )

    if not github_mcp_server_path:
        print("Error: GITHUB_MCP_SERVER environment variable is not set.")
        return None

    server_cmd = f"{github_mcp_server_path} --toolsets {toolsets}"
    if read_only:
        server_cmd += " --read-only"
    server_cmd += " stdio"

    base_command = [
        mcpcurl_path,
        "--stdio-server-cmd",
        server_cmd,
        "tools",
        tool_name,
        * _build_mcpcurl_args(arguments),
    ]

    # Merge with the parent env: Windows subprocesses need SystemRoot/PATH etc.
    env = {
        **os.environ,
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