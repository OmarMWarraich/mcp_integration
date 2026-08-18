# GitHub MCP CrewAI Integration

A Django + CrewAI application that analyzes GitHub repositories using the **GitHub MCP Server** via `mcpcurl`. It orchestrates a crew of agents to generate repository documentation, summarize open issues, and report on recent pull requests.

---

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Usage](#usage)
- [MCP Tool Wrapper](#mcp-tool-wrapper)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Coming Next](#coming-next)

---

## Description

This project combines Django as the web orchestration layer with CrewAI agents that use GitHub MCP tools directly. Instead of hand-written REST calls to the GitHub API, every read operation goes through the official GitHub MCP Server using the generated `mcpcurl` CLI contract. This ensures the tools stay aligned with the live MCP schema and avoids drift from manual API bindings.

The current workflow accepts a GitHub repository URL, runs three CrewAI tasks sequentially, and produces a combined Markdown summary rendered as HTML.

---

## Features

### Existing

- **Django web interface** for submitting a GitHub repository URL and viewing generated documentation.
- **CrewAI agent crew** with three specialized agents:
  - `repo_structure_auditor` — lists repository files via MCP `get_file_contents`.
  - `issue_analyst` — fetches open issues via MCP `list_issues`.
  - `pull_requests_fetcher_reporter` — fetches open pull requests via MCP `list_pull_requests`.
- **MCP-first tool execution** through a centralized `mcp_tool()` helper in `mcp_manager/utils.py`.
- **Dynamic CLI flag generation** from argument dictionaries so wrappers match the generated `mcpcurl` tool schema.
- **Read-only mode support** for MCP toolsets that include write tools with incompatible schemas (e.g. `issues`).
- **Combined Markdown output** converted to HTML for browser display.
- **Unit tests** covering the MCP helper, toolset selection, and issue wrapper contract.

### Coming Soon

- Branch listing and commit history reports.
- Code search and security advisory summaries.
- Persistent storage of generated documents with the existing `GeneratedDocument` model.
- REST API endpoint for headless execution.
- Async Celery task queue for long-running crews.
- Configurable LLM model selection from the UI.

---

## Architecture

```text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Django Web UI  │────▶│  CrewAI Process  │────▶│  MCP Tool Wrappers  │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │   mcpcurl    │
                                                  └──────────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │ GitHub MCP Server │
                                                │   (stdio/spawn)  │
                                                └──────────────────┘
                                                         │
                                                         ▼
                                                  ┌─────────────┐
                                                  │ GitHub API  │
                                                  └─────────────┘
```

Key files:

- [mcp_manager/utils.py](mcp_manager/utils.py) — central `mcp_tool()` helper.
- [mcp_manager/tools/directory_scanner.py](mcp_manager/tools/directory_scanner.py) — `get_repo_files` tool.
- [mcp_manager/tools/issue_retriever.py](mcp_manager/tools/issue_retriever.py) — `get_issue` tool.
- [mcp_manager/tools/pull_request_lister.py](mcp_manager/tools/pull_request_lister.py) — `get_pull_requests` tool.
- [mcp_manager/agents/agents.py](mcp_manager/agents/agents.py) — agent definitions.
- [mcp_manager/tasks/tasks.py](mcp_manager/tasks/tasks.py) — task definitions.
- [mcp_manager/crews/crew.py](mcp_manager/crews/crew.py) — crew assembly.

---

## Prerequisites

- Python 3.12+
- Git
- A local copy of the [GitHub MCP Server](https://github.com/github/github-mcp-server) binary
- A GitHub personal access token
- An OpenAI API key (for CrewAI LLM)

Tested dependency versions:

| Package | Version |
| --- | --- |
| Django | 6.1 |
| crewai | 1.15.16 |
| langchain-openai | 1.5.1 |
| openai | 2.54.0 |
| Markdown | 3.10.3 |
| requests | 2.34.2 |

---

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd mcp_integration
   ```

2. Create and activate a virtual environment:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dependencies:

   ```bash
   pip install django crewai langchain-openai requests markdown
   ```

4. Build or obtain the GitHub MCP Server binary and `mcpcurl`:

   ```bash
   # Example: place the compiled github-mcp-server binary next to this project
   # /Users/owa/code/ai/agentic-workflow-crew-ai/github-mcp-server/github-mcp-server
   # Copy or symlink the mcpcurl binary into this project root
   ln -s /path/to/mcpcurl ./mcpcurl
   ```

5. Run Django migrations:

   ```bash
   python manage.py migrate
   ```

---

## Configuration

Create a `.env` file in the project root with the following variables:

```env
SECRET_KEY=your-django-secret-key
OPENAI_API_KEY=sk-...
GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
GITHUB_MCP_SERVER=/absolute/path/to/github-mcp-server
```

The project expects:

- `mcpcurl` to be located in the project root (`./mcpcurl`).
- `GITHUB_MCP_SERVER` to point to the executable GitHub MCP Server binary.

The GitHub token is forwarded to the MCP server process at runtime.

---

## Running the Project

Start the development server:

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and paste a GitHub repository URL such as:

```text
https://github.com/github/github-mcp-server
```

The crew will run and return a combined HTML report.

---

## Usage

### Direct tool smoke test

You can test the MCP wrappers from a Django shell:

```bash
python manage.py shell
```

```python
from mcp_manager.tools.issue_retriever import get_issue
print(get_issue.run(owner="github", repo="github-mcp-server"))
```

### Run the test suite

```bash
python manage.py test mcp_manager -v 2
```

---

## MCP Tool Wrapper

`mcp_manager.utils.mcp_tool()` is the single gateway to the GitHub MCP Server.

```python
mcp_tool(
    tool_name="list_issues",
    arguments={"owner": "github", "repo": "github-mcp-server", "state": "OPEN", "perPage": 5},
    toolsets="issues",
    read_only=True,
)
```

It translates the `arguments` dict into `--flag value` pairs expected by `mcpcurl tools <name>`.

Important notes:

- Some toolsets include write tools whose union-typed schemas break `mcpcurl`'s dynamic command generation. The symptom is `unknown flag: --owner`. Pass `read_only=True` to exclude those write tools.
- The default toolset is `repos`, which is the minimal schema that always loads cleanly.

---

## Testing

The test suite covers:

- MCP CLI flag generation
- Default and custom toolset selection
- `read_only` flag injection
- Issue wrapper schema contract

Run all tests:

```bash
.venv/bin/python manage.py test mcp_manager -v 2
```

---

## Troubleshooting

### `unknown flag: --owner`

This happens when the selected toolset schema contains a property type that `mcpcurl` cannot parse. The fix is to pass `read_only=True` to `mcp_tool()` when invoking read tools from toolsets that also contain write tools (e.g. `issues`).

### `mcpcurl stdout is not valid JSON`

Check the printed command in the terminal and run it manually to see the raw server error. Usually this indicates a missing or invalid `GITHUB_PERSONAL_ACCESS_TOKEN`.

### `GITHUB_MCP_SERVER environment variable is not set`

Ensure `.env` exists at the project root and contains `GITHUB_MCP_SERVER=/absolute/path/to/github-mcp-server`.

---

## Coming Next

- [ ] Add branch and commit report agents.
- [ ] Add code search and security advisory agents.
- [ ] Persist generated reports via `GeneratedDocument` model.
- [ ] Add a JSON API endpoint for headless usage.
- [ ] Run crews asynchronously with Celery.
- [ ] Allow model selection and temperature tuning from the UI.
