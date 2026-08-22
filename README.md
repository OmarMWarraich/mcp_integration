# GitHub MCP CrewAI Integration

A Django + CrewAI application that analyzes GitHub repositories using the **GitHub MCP Server** via `mcpcurl`. It orchestrates a crew of agents to generate repository documentation, summarize open issues, and report on recent pull requests.

---

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Building the MCP Binaries](#building-the-mcp-binaries)
- [Configuration](#configuration)
- [RabbitMQ Setup](#rabbitmq-setup)
- [PostgreSQL Migration](#postgresql-migration)
- [Celery Result Backend](#celery-result-backend)
- [Celery Setup](#celery-setup)
- [Running the Project](#running-the-project)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [MCP Tool Wrapper](#mcp-tool-wrapper)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Coming Next](#coming-next)

---

## Description

This project combines Django as the web orchestration layer with CrewAI agents that use GitHub MCP tools directly. Instead of hand-written REST calls to the GitHub API, every read operation goes through the official GitHub MCP Server using the generated `mcpcurl` CLI contract. This ensures the tools stay aligned with the live MCP schema and avoids drift from manual API bindings.

The current workflow accepts a GitHub repository URL, runs four CrewAI tasks sequentially, and produces a combined Markdown summary rendered as HTML.

---

## Features

### Existing

- **Django web interface** for submitting a GitHub repository URL and viewing generated documentation.
- **CrewAI agent crew** with four specialized agents:
  - `repo_structure_auditor` — lists repository files via MCP `get_file_contents`.
  - `issue_analyst` — fetches open issues via MCP `list_issues`.
  - `pull_requests_fetcher_reporter` — fetches open pull requests via MCP `list_pull_requests`.
  - `branch_reporter` — fetches repository branches via MCP `list_branches`.
- **MCP-first tool execution** through a centralized `mcp_tool()` helper in `mcp_manager/utils.py`.
- **Dynamic CLI flag generation** from argument dictionaries so wrappers match the generated `mcpcurl` tool schema.
- **Read-only mode support** for MCP toolsets that include write tools with incompatible schemas (e.g. `issues`).
- **Combined Markdown output** converted to HTML for browser display.
- **Unit tests** covering the MCP helper, toolset selection, and issue wrapper contract.

### Coming Soon

- Commit history reports.
- Code search and security advisory summaries.
- Persistent storage of generated documents with the existing `GeneratedDocument` model.
- REST API endpoint for headless execution.
- Async Celery task queue for long-running crews.
- Configurable LLM model selection from the UI.

---

## Architecture

```text
                         ┌─────────────────────────────────────┐
                         │         Clients / Users             │
                         │  • Django Web UI (browser)          │
                         │  • REST API clients (curl/scripts)  │
                         └──────────────┬──────────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────────────┐
                         │           Django Layer              │
                         │  • mcp_manager/views.py             │
                         │    - POST /run-crew/                │
                         │    - GET  /crew-status/<id>/        │
                         │  • Django admin & web templates     │
                         └──────────────┬──────────────────────┘
                                        │ enqueue / poll
                                        ▼
                         ┌─────────────────────────────────────┐
                         │      Celery Distributed Queue       │
                         │                                     │
                         │   ┌──────────┐      ┌──────────┐   │
                         │   │ RabbitMQ │      │  Redis   │   │
                         │   │  broker  │      │  result  │   │
                         │   │ :5672    │      │ backend  │   │
                         │   └────┬─────┘      │ :6379    │   │
                         │        │            └────┬─────┘   │
                         │        └─────────────────┘           │
                         │                  │                    │
                         └──────────────────┼────────────────────┘
                                            │
                                            ▼
                         ┌─────────────────────────────────────┐
                         │         Celery Worker               │
                         │  • run_crew_task                    │
                         │  • run_multiple_crews_task          │
                         │  • run_scheduled_crew_task          │
                         │        │                            │
                         │        ▼                            │
                         │  ┌──────────────────────┐           │
                         │  │   CrewAI Process     │           │
                         │  │  • build_crew()      │           │
                         │  │  • agents & tasks    │           │
                         │  └──────────┬───────────┘           │
                         │             │                       │
                         │             ▼                       │
                         │  ┌──────────────────────┐           │
                         │  │   MCP Tool Wrappers  │           │
                         │  │  • directory_scanner │           │
                         │  │  • issue_retriever   │           │
                         │  │  • pull_request_...  │           │
                         │  │  • branch_lister     │           │
                         │  └──────────┬───────────┘           │
                         │             │                       │
                         └─────────────┼───────────────────────┘
                                       ▼
                         ┌─────────────────────────────────────┐
                         │   Infrastructure (Docker Compose)   │
                         │  ┌──────────────┐ ┌──────────────┐  │
                         │  │  PostgreSQL  │ │    Redis     │  │
                         │  │   :5432      │ │   :6379      │  │
                         │  │  persistent  │ │  transient   │  │
                         │  │  task/Django │ │  results     │  │
                         │  └──────────────┘ └──────────────┘  │
                         │  ┌────────────────────────────────┐ │
                         │  │  RabbitMQ :5672 / :15672       │ │
                         │  │  Celery broker / management UI │ │
                         │  └────────────────────────────────┘ │
                         └─────────────────────────────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────────────────┐
                         │       GitHub MCP Server Runtime     │
                         │         • mcpcurl CLI               │
                         │         • stdio subprocess          │
                         └──────────────┬──────────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────────────┐
                         │           GitHub API                │
                         └─────────────────────────────────────┘
```

### Request flow

1. A user submits a repo via the Django web UI or a `POST /run-crew/` API call.
2. The Django view validates the payload and enqueues a Celery task on RabbitMQ.
3. The Celery worker picks up the task, builds the CrewAI crew, and executes agents.
4. Agents invoke MCP tool wrappers, which spawn `mcpcurl` and the GitHub MCP Server.
5. Task results are written to Redis and exposed through `GET /crew-status/<task_id>/`.
6. PostgreSQL stores Django state, sessions, and future persistent report models.

### Key files

- [mcp_manager/views.py](mcp_manager/views.py) — Django API endpoints.
- [mcp_manager/tasks/celery_tasks.py](mcp_manager/tasks/celery_tasks.py) — async Celery task definitions.
- [mcp_integration/celery.py](mcp_integration/celery.py) — Celery app bootstrap.
- [mcp_integration/settings.py](mcp_integration/settings.py) — broker/backend configuration.
- [mcp_manager/crews/crew.py](mcp_manager/crews/crew.py) — crew assembly.
- [mcp_manager/agents/agents.py](mcp_manager/agents/agents.py) — agent definitions.
- [mcp_manager/tasks/tasks.py](mcp_manager/tasks/tasks.py) — CrewAI task definitions.
- [mcp_manager/utils.py](mcp_manager/utils.py) — central `mcp_tool()` helper.
- [mcp_manager/tools/directory_scanner.py](mcp_manager/tools/directory_scanner.py) — repo file tool.
- [mcp_manager/tools/issue_retriever.py](mcp_manager/tools/issue_retriever.py) — issues tool.
- [mcp_manager/tools/pull_request_lister.py](mcp_manager/tools/pull_request_lister.py) — PR tool.
- [mcp_manager/tools/branch_lister.py](mcp_manager/tools/branch_lister.py) — branches tool.

---

## Prerequisites

- Python 3.12+
- Git
- Docker & Docker Compose (for PostgreSQL, RabbitMQ, and Redis)
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
| psycopg | 3.3.4 |
| redis | 8.1.0 |
| celery | 5.6.3 |

---

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd mcp_integration
   ```

2. Create and activate a virtual environment:

   **Unix (macOS / Linux):**

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install Python dependencies:

   ```bash
   pip install django crewai langchain-openai requests markdown psycopg[binary] redis celery
   ```

4. Build or obtain the GitHub MCP Server binary and `mcpcurl` — see
   [Building the MCP Binaries](#building-the-mcp-binaries) for full instructions.

   In short, on any OS with Go installed:

   ```bash
   go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest
   go install github.com/github/github-mcp-server/cmd/mcpcurl@latest
   ```

   then copy the resulting binaries (`.exe` on Windows) into the project root.

5. Run Django migrations:

   ```bash
   python manage.py migrate
   ```

---

## Building the MCP Binaries

The project needs two executables in the project root, built for **your** OS:

| Binary | Unix name | Windows name | Purpose |
| --- | --- | --- | --- |
| GitHub MCP Server | `github-mcp-server` | `github-mcp-server.exe` | Serves GitHub MCP tools over stdio |
| mcpcurl | `mcpcurl` | `mcpcurl.exe` | CLI client that spawns the server and invokes tools |

> **Important:** A binary built on macOS/Linux will fail on Windows with
> `[WinError 193] %1 is not a valid Win32 application`, and vice versa.
> `github-mcp-server` has prebuilt releases for all platforms, but `mcpcurl`
> has **no prebuilt release** and must be built from source with Go.

### Prerequisites

- [Go](https://go.dev/dl/) 1.22 or newer (`go version` to verify).

### Option A — `go install` (recommended)

Builds both binaries for your current OS/architecture straight from the module proxy.

**Unix (macOS / Linux):**

```bash
go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest
go install github.com/github/github-mcp-server/cmd/mcpcurl@latest

# Copy or symlink both binaries into the project root
ln -s "$(go env GOPATH)/bin/github-mcp-server" ./github-mcp-server
ln -s "$(go env GOPATH)/bin/mcpcurl" ./mcpcurl
```

**Windows (PowerShell):**

```powershell
go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest
go install github.com/github/github-mcp-server/cmd/mcpcurl@latest

# Copy the .exe files into the project root
$gobin = "$(go env GOPATH)\bin"
Copy-Item "$gobin\github-mcp-server.exe", "$gobin\mcpcurl.exe" -Destination .
```

### Option B — build from a cloned repository

Useful if you want to pin a specific version or modify the source.

**Unix (macOS / Linux):**

```bash
git clone https://github.com/github/github-mcp-server.git
cd github-mcp-server
go build -o /path/to/mcp_integration/github-mcp-server ./cmd/github-mcp-server
go build -o /path/to/mcp_integration/mcpcurl ./cmd/mcpcurl
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/github/github-mcp-server.git
cd github-mcp-server
go build -o C:\path\to\mcp_integration\github-mcp-server.exe .\cmd\github-mcp-server
go build -o C:\path\to\mcp_integration\mcpcurl.exe .\cmd\mcpcurl
```

### Option C — prebuilt server release (server only)

Download `github-mcp-server` for your platform from the
[releases page](https://github.com/github/github-mcp-server/releases/latest)
(e.g. `github-mcp-server_Windows_x86_64.zip` or `github-mcp-server_Darwin_arm64.tar.gz`),
extract it into the project root. You still need to build `mcpcurl` with Option A or B.

### Cross-compiling

Go can build for another OS from any machine, e.g. Windows binaries from macOS/Linux:

```bash
GOOS=windows GOARCH=amd64 go build -o mcpcurl.exe ./cmd/mcpcurl
GOOS=windows GOARCH=amd64 go build -o github-mcp-server.exe ./cmd/github-mcp-server
```

### Verify the binaries

**Unix:**

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
./mcpcurl --stdio-server-cmd "./github-mcp-server --toolsets repos stdio" tools get_file_contents --owner github --repo github-mcp-server --path /
```

**Windows (PowerShell):**

```powershell
$env:GITHUB_PERSONAL_ACCESS_TOKEN = "github_pat_..."
.\mcpcurl.exe --stdio-server-cmd ".\github-mcp-server.exe --toolsets repos stdio" tools get_file_contents --owner github --repo github-mcp-server --path /
```

A JSON array of repository files confirms both binaries work. The `mcp_tool()` helper
automatically picks `mcpcurl.exe` on Windows and `mcpcurl` on Unix.

---

## Configuration

Create a `.env` file in the project root with the following variables:

**Unix (macOS / Linux):**

```env
SECRET_KEY=your-django-secret-key
OPENAI_API_KEY=sk-...
GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
GITHUB_MCP_SERVER=./github-mcp-server

# PostgreSQL
DB_NAME=mcp_integration
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

# Celery
BROKER_URL=amqp://user:pass@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**Windows:** identical, except the server binary needs the `.exe` extension:

```env
GITHUB_MCP_SERVER=./github-mcp-server.exe
```

The project expects:

- `mcpcurl` (Unix) or `mcpcurl.exe` (Windows) to be located in the project root.
- `GITHUB_MCP_SERVER` to point to the executable GitHub MCP Server binary for your OS.

The GitHub token is forwarded to the MCP server process at runtime.

---

## RabbitMQ Setup

The async Celery pipeline uses RabbitMQ as its message broker.

### Start RabbitMQ with Docker Compose

From the project root, run:

```bash
docker compose up -d rabbitmq
```

This starts:

- RabbitMQ AMQP broker on `localhost:5672`
- RabbitMQ Management UI on [http://localhost:15672](http://localhost:15672) (login: `user` / `pass`)

### Stop RabbitMQ

```bash
docker compose down
```

To remove the persisted volume as well:

```bash
docker compose down -v
```

### Verify the broker is reachable

```bash
docker exec mcp_integration_rabbitmq rabbitmq-diagnostics ping
```

You should see `Health check passed`.

### Manual installation (alternative)

If you prefer not to use Docker, install RabbitMQ natively:

**Unix (macOS):**

```bash
brew install rabbitmq
brew services start rabbitmq
```

**Windows (PowerShell):**

```powershell
choco install rabbitmq
# or download the installer from https://www.rabbitmq.com/docs/install-windows
```

Then update `BROKER_URL` in `.env` to point to your local broker (e.g. `amqp://guest:guest@localhost:5672//`).

> **Note:** The default `.env` uses `localhost` because RabbitMQ is exposed on the host. If you later run the Django app or Celery workers inside the Docker Compose network, change the host to `rabbitmq` (the service name).

### Avoiding port conflicts

If you have a local RabbitMQ instance already running on port 5672, stop it before starting the Docker container:

**Unix (macOS):**

```bash
brew services stop rabbitmq
```

**Windows (PowerShell):**

```powershell
Stop-Service RabbitMQ
```

---

## PostgreSQL Migration

The project uses PostgreSQL instead of SQLite for concurrency-safe operations.

### Start PostgreSQL with Docker Compose

From the project root, start the infrastructure stack:

```bash
docker compose up -d
```

This starts PostgreSQL on `localhost:5432` with the credentials defined in `docker-compose.yml`.

### Create the application database

The first time you start the container, create the database:

```bash
docker exec mcp_integration_db psql -U postgres -c "CREATE DATABASE mcp_integration;"
```

### Run Django migrations

```bash
python manage.py migrate
```

### PostgreSQL environment variables

Django reads the database connection from `.env`:

```env
DB_NAME=mcp_integration
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432
```

### Avoiding port conflicts

If you have a local PostgreSQL instance already running on port 5432, stop it before starting the Docker container:

**Unix (macOS):**

```bash
brew services stop postgresql
```

**Windows (PowerShell):**

```powershell
Stop-Service postgresql*
```

---

## Celery Result Backend

Celery task results are stored in **Redis**.

The Redis service is defined in `docker-compose.yml` and exposed on `localhost:6379`.

Configure the backend in `.env`:

```env
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Why Redis for results?

- Fast, in-memory storage for transient task metadata.
- Simple to run alongside RabbitMQ in Docker Compose.
- Can be swapped for PostgreSQL later if persistence requirements change.

---

## Celery Setup

Celery is integrated with Django using RabbitMQ as the broker and Redis as the result backend.

Key files:

- [mcp_integration/celery.py](mcp_integration/celery.py) — Celery app configuration.
- [mcp_manager/tasks/celery_tasks.py](mcp_manager/tasks/celery_tasks.py) — async crew task definition.

### Configuration

Celery reads the following settings from `.env` via `mcp_integration/settings.py`:

```env
BROKER_URL=amqp://user:pass@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Start a Celery worker

Make sure RabbitMQ and Redis are running, then run:

**Unix (macOS / Linux):**

```bash
celery -A mcp_integration worker --loglevel=info
```

For production-style deployments, you can tune concurrency:

```bash
celery -A mcp_integration worker --loglevel=info --concurrency=4
```

**Windows (PowerShell):**

Celery's default prefork pool is not supported on Windows — use the `solo` pool:

```powershell
celery -A mcp_integration worker --loglevel=info --pool=solo
```

### Inspect registered tasks

```bash
celery -A mcp_integration inspect registered
```

You should see:

- `mcp_manager.tasks.celery_tasks.run_crew_task`
- `mcp_manager.tasks.celery_tasks.run_multiple_crews_task`
- `mcp_manager.tasks.celery_tasks.run_scheduled_crew_task`

### Available tasks

| Task | Purpose |
| --- | --- |
| `run_crew_task` | Run the analysis crew for a single repository and persist the HTML report. |
| `run_multiple_crews_task` | Dispatch crews for many repositories via a Celery group; returns child task IDs. |
| `run_scheduled_crew_task` | Dedicated entry point for Celery Beat scheduled runs. |
| `validate_crew_payload` | Pre-flight validation for batch payloads. |

### Result payload

Successful single-repo crew tasks persist a sanitized HTML report as a
`GeneratedDocument` row and return a structured JSON-serializable payload:

```json
{
  "task_id": "a1b2c3d4-...",
  "owner": "github",
  "repo": "github-mcp-server",
  "status": "SUCCESS",
  "document_id": 42,
  "serialized_at": 1692432000.0
}
```

Batch tasks (`run_multiple_crews_task`) return immediately with the dispatched
child task IDs; poll each child via `GET /crew-status/<child_task_id>/`:

```json
{
  "task_id": "parent-id-...",
  "status": "SUCCESS",
  "count": 2,
  "children": [
    {"task_id": "child-1-...", "owner": "github", "repo": "github-mcp-server"},
    {"task_id": "child-2-...", "owner": "django", "repo": "django"}
  ]
}
```

On failure, Celery marks the task as `FAILURE` and stores the raised exception in the result backend. When polling via `GET /crew-status/<task_id>/`, you will receive:

    {
      "task_id": "a1b2c3d4-...",
      "status": "FAILURE",
      "error": "ExceptionName",
      "message": "..."
    }

Each task is retried up to three times with exponential backoff before a failure is recorded.

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

The crew run is dispatched to Celery (a worker must be running); the page polls
the task status every 5 seconds and reloads with the combined HTML report when
the run completes. Each run writes its intermediate markdown files to an
isolated `generated_docs/<task_id>/` directory, so concurrent runs are safe.

---

## Usage

### Async crew execution with Celery

1. Make sure RabbitMQ and Redis are running:

   ```bash
   docker compose up -d
   ```

2. Start a Celery worker:

   ```bash
   celery -A mcp_integration worker --loglevel=info
   ```

3. Dispatch a task from a Django shell, view, or API:

   ```python
   from mcp_manager.tasks.celery_tasks import run_crew_task

   task = run_crew_task.delay(owner="github", repo="github-mcp-server")
   print(task.id)  # e.g. a1b2c3d4-...
   ```

4. Check the result:

   ```python
   result = run_crew_task.AsyncResult(task.id)
   print(result.status)  # PENDING / STARTED / SUCCESS / FAILURE
   print(result.result)  # payload once SUCCESS
   ```

### Trigger via HTTP API

Start the Django development server and Celery worker, then trigger a run:

```bash
curl -X POST http://127.0.0.1:8000/run-crew/ \
  -H "Content-Type: application/json" \
  -d '{"owner": "github", "repo": "github-mcp-server"}'
```

Response:

```json
{"task_id": "a1b2c3d4-...", "status": "PENDING"}
```

For multiple repos the response contains the child task IDs; poll each one
via `/crew-status/<child_task_id>/`:

```bash
curl -X POST http://127.0.0.1:8000/run-crew/ \
  -H "Content-Type: application/json" \
  -d '{"repos": [{"owner": "github", "repo": "github-mcp-server"}, {"owner": "django", "repo": "django"}]}'
```

```json
{
  "task_id": "parent-id-...",
  "status": "SUCCESS",
  "count": 2,
  "children": [
    {"task_id": "child-1-...", "owner": "github", "repo": "github-mcp-server"},
    {"task_id": "child-2-...", "owner": "django", "repo": "django"}
  ]
}
```

### Check task status via API

```bash
curl http://127.0.0.1:8000/crew-status/a1b2c3d4-.../
```

Possible statuses: `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`.

---

## API Endpoints

| Method | Endpoint | Body | Response |
| --- | --- | --- | --- |
| `POST` | `/generate/` | `repo_url` | HTML form redirect |
| `POST` | `/generate-multiple/` | `repo_urls` (textarea) | HTML form redirect |
| `POST` | `/run-crew/` | `{"owner": "...", "repo": "..."}` or `{"repos": [...]}` | `{"task_id": "...", "status": "PENDING"}` |
| `GET` | `/crew-status/<task_id>/` | — | `{"task_id": "...", "status": "...", "result": {...}}` |
| `GET` | `/history/` | — | HTML report history |

### `POST /run-crew/`

Trigger a single crew run:

```bash
curl -X POST http://127.0.0.1:8000/run-crew/ \
  -H "Content-Type: application/json" \
  -d '{"owner": "github", "repo": "github-mcp-server"}'
```

Trigger multiple crew runs concurrently:

```bash
curl -X POST http://127.0.0.1:8000/run-crew/ \
  -H "Content-Type: application/json" \
  -d '{"repos": [{"owner": "github", "repo": "github-mcp-server"}]}'
```

### `GET /crew-status/<task_id>/`

Poll for the result of a previously triggered task:

```bash
curl http://127.0.0.1:8000/crew-status/a1b2c3d4-.../
```

> **CSRF:** `POST /run-crew/` is protected by Django's CSRF middleware. Browser
> clients must send the `X-CSRFToken` header (the token is set as the
> `csrftoken` cookie after any GET). Headless clients should first GET a page
> to obtain the cookie, or the endpoint can be placed behind token auth in
> production.

### Run multiple crews concurrently

```python
from mcp_manager.tasks.celery_tasks import run_multiple_crews_task

repos = [
    {"owner": "github", "repo": "github-mcp-server"},
    {"owner": "django", "repo": "django"},
]
task = run_multiple_crews_task.delay(repos)
print(task.id)
```

### Scheduled crew execution with Celery Beat

Add a Beat schedule entry in `mcp_integration/settings.py`:

```python
CELERY_BEAT_SCHEDULE = {
    "analyze-github-mcp-server-hourly": {
        "task": "mcp_manager.tasks.celery_tasks.run_scheduled_crew_task",
        "schedule": 3600.0,  # seconds
        "args": ("github", "github-mcp-server"),
    },
}
```

Then start the scheduler alongside a worker:

```bash
# Terminal 1: worker
celery -A mcp_integration worker --loglevel=info

# Terminal 2: scheduler
celery -A mcp_integration beat --loglevel=info
```

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
- Branch wrapper schema contract

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

### PostgreSQL: `database "mcp_integration" does not exist`

Create the database inside the running container:

```bash
docker exec mcp_integration_db psql -U postgres -c "CREATE DATABASE mcp_integration;"
```

Then re-run migrations:

```bash
python manage.py migrate
```

### PostgreSQL: `could not connect to server: Connection refused`

1. Confirm the container is running:

   ```bash
   docker compose ps
   ```

2. Verify `DB_HOST=localhost` and `DB_PORT=5432` in `.env`.
3. Make sure no other PostgreSQL instance is bound to port 5432:

   ```bash
   lsof -i :5432
   brew services stop postgresql
   ```

### DB locks / slow writes / `database is locked`

This is the classic symptom of running SQLite under concurrency. The project now uses PostgreSQL to avoid this. If you still see `database is locked`, verify your `DATABASES` setting in `mcp_integration/settings.py` points to PostgreSQL, not SQLite.

If locks occur in PostgreSQL:

- Look for long-running transactions in the worker logs.
- Restart stuck workers.
- If tasks are being redelivered with RabbitMQ, look for worker crashes / lost heartbeats and review acknowledgement-related settings such as `CELERY_TASK_ACKS_LATE` and `CELERY_WORKER_PREFETCH_MULTIPLIER`. (The `visibility_timeout` option applies to Redis/SQS brokers, not RabbitMQ.)

### RabbitMQ / broker connection issues

Symptoms include:

- `amqp.exceptions.AccessRefused`
- `Connection refused` from Celery
- Worker starts but shows `Connected to amqp://guest:**@127.0.0.1:5672//` instead of your configured broker

Fix:

1. Confirm RabbitMQ is running:

   ```bash
   docker exec mcp_integration_rabbitmq rabbitmq-diagnostics ping
   ```

2. Check that `BROKER_URL` in `.env` matches the RabbitMQ credentials:

   ```env
   BROKER_URL=amqp://user:pass@localhost:5672//
   ```

3. Stop any local RabbitMQ instance that may be shadowing the Docker port:

   ```bash
   brew services stop rabbitmq
   ```

4. Verify the management UI is reachable at [http://localhost:15672](http://localhost:15672).

### Celery worker crashes or exits immediately

Common causes and fixes:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError` on startup | Worker started from wrong directory | Run from project root where `manage.py` lives. |
| `AttributeError: 'Settings' object has no attribute '...'` | Missing env variable in `.env` | Ensure `.env` is loaded; run with `.venv/bin/python -m celery ...` if needed. |
| Worker consumes memory until killed | CrewAI output is large; no result size limits | Use `--max-tasks-per-child=50` to recycle workers. |
| `Received unregistered task` | Celery did not autodiscover tasks | Restart worker; check `celery -A mcp_integration inspect registered`. |
| Tasks stay in `PENDING` | No worker is running, or worker is connected to a different broker | Start a worker and confirm broker URL. |
| Worker dies with `OperationalError` | Cannot reach PostgreSQL, Redis, or RabbitMQ | Verify all Docker services are healthy (`docker compose ps`). |

### Redis result backend errors

If task statuses never progress from `PENDING`:

1. Confirm Redis is running:

   ```bash
   docker exec mcp_integration_redis redis-cli ping
   # expected: PONG
   ```

2. Verify `CELERY_RESULT_BACKEND=redis://localhost:6379/0` in `.env`.
3. Make sure no other Redis instance is on port 6379:

   ```bash
   lsof -i :6379
   ```

### Worker logs show tasks but no output appears

- Check that the worker and the Django app share the same `BROKER_URL` and `CELERY_RESULT_BACKEND` values.
- Look for `Process exited with '1'` in the worker log, which often means the task raised an exception. Inspect the traceback and fix the underlying issue.
- Ensure `GITHUB_MCP_SERVER` and `GITHUB_PERSONAL_ACCESS_TOKEN` are set in the worker's environment, not just the Django server environment.

---

## Coming Next

- [ ] Add branch and commit report agents.
- [ ] Add code search and security advisory agents.
- [ ] Persist generated reports via `GeneratedDocument` model.
- [ ] Add a JSON API endpoint for headless usage.
- [ ] Run crews asynchronously with Celery.
- [ ] Allow model selection and temperature tuning from the UI.
