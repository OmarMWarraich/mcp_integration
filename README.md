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

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dependencies:

   ```bash
   pip install django crewai langchain-openai requests markdown psycopg[binary] redis celery
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

The project expects:

- `mcpcurl` to be located in the project root (`./mcpcurl`).
- `GITHUB_MCP_SERVER` to point to the executable GitHub MCP Server binary.

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

If you prefer not to use Docker, install RabbitMQ via Homebrew:

```bash
brew install rabbitmq
brew services start rabbitmq
```

Then update `BROKER_URL` in `.env` to point to your local broker (e.g. `amqp://guest:guest@localhost:5672//`).

> **Note:** The default `.env` uses `localhost` because RabbitMQ is exposed on the host. If you later run the Django app or Celery workers inside the Docker Compose network, change the host to `rabbitmq` (the service name).

### Avoiding port conflicts

If you have a local RabbitMQ instance already running on port 5672 (e.g. from Homebrew), stop it before starting the Docker container:

```bash
brew services stop rabbitmq
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

If you have a local PostgreSQL instance already running on port 5432 (e.g. from Homebrew), stop it before starting the Docker container:

```bash
brew services stop postgresql
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

```bash
celery -A mcp_integration worker --loglevel=info
```

For production-style deployments, you can tune concurrency:

```bash
celery -A mcp_integration worker --loglevel=info --concurrency=4
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
| `run_crew_task` | Run the analysis crew for a single repository. |
| `run_multiple_crews_task` | Run crews for many repositories concurrently using a Celery group. |
| `run_scheduled_crew_task` | Dedicated entry point for Celery Beat scheduled runs. |
| `validate_crew_payload` | Pre-flight validation for batch payloads. |

### Result payload

Successful crew tasks return a structured JSON-serializable payload:

```json
{
  "task_id": "a1b2c3d4-...",
  "owner": "github",
  "repo": "github-mcp-server",
  "status": "SUCCESS",
  "raw_output": "...",
  "serialized_at": 1692432000.0
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

The crew will run and return a combined HTML report.

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

For multiple repos:

```bash
curl -X POST http://127.0.0.1:8000/run-crew/ \
  -H "Content-Type: application/json" \
  -d '{"repos": [{"owner": "github", "repo": "github-mcp-server"}, {"owner": "django", "repo": "django"}]}'
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
| `POST` | `/run-crew/` | `{"owner": "...", "repo": "..."}` or `{"repos": [...]}` | `{"task_id": "...", "status": "PENDING"}` |
| `GET` | `/crew-status/<task_id>/` | — | `{"task_id": "...", "status": "...", "result": {...}}` |

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
