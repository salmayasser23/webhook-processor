# Webhook Processor

A containerized REST API for receiving, processing, and storing webhook alerts. Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, and **Docker Compose**.

The service accepts JSON alerts, simulates a three-second processing task without blocking other requests, and persists the results so they can be retrieved later. Duplicate webhook deliveries are handled safely using the event ID.

## Features

- **Webhook ingestion:** `POST /webhook` accepts and validates incoming alerts.
- **Asynchronous processing:** New alerts undergo a configurable delay (three seconds by default) using `asyncio.sleep`.
- **Persistent storage:** Processed alerts are stored in PostgreSQL and retained in a Docker volume.
- **Idempotency:** Repeating an identical event returns the existing record instead of creating a duplicate.
- **Conflict detection:** Reusing an event ID with different content returns `409 Conflict`.
- **Alert retrieval:** `GET /alerts` returns processed alerts, newest first.
- **Health monitoring:** `GET /health` checks database connectivity.
- **Reproducible setup:** Docker Compose starts PostgreSQL, applies database migrations, and launches the API.
- **Automated checks:** Unit tests, a PostgreSQL-backed smoke test, linting, and a GitHub Actions workflow are included.

## Tech Stack

| Component | Technology |
| --- | --- |
| API | Python 3.12, FastAPI, Uvicorn |
| Database | PostgreSQL 17 |
| Data access | SQLAlchemy (async) and asyncpg |
| Schema migrations | Alembic |
| Validation and configuration | Pydantic, pydantic-settings |
| Containerization | Docker, Docker Compose |
| Testing and linting | pytest, HTTPX, Ruff |
| CI | GitHub Actions |

## Quick Start (Docker)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with the Compose plugin
- Python 3.12 (only needed to run the local smoke test or unit tests)

### 1. Open the project

Clone this repository using the **Code → HTTPS** link on GitHub, or download its source files. Open a terminal in the project root (the folder containing `docker-compose.yml`).

### 2. Configure the environment

Copy the example configuration to a local `.env` file.

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Edit `.env` and replace the example database password with your own value:

```dotenv
POSTGRES_USER=webhook_user
POSTGRES_PASSWORD=replace_with_a_strong_password
POSTGRES_DB=webhook_db
PROCESSING_DELAY_SECONDS=3
```

The `.env` file is excluded from Git and Docker build contexts. Do not commit it or use production secrets in `.env.example`.

### 3. Start the application

```bash
docker compose up -d --build
```

Docker Compose will:

1. Start PostgreSQL and wait for it to become healthy.
2. Apply the Alembic database migrations.
3. Start the FastAPI service.

Check that the services started:

```bash
docker compose ps
```

Once the API is ready, open:

| Resource | Local URL |
| --- | --- |
| Interactive API documentation (Swagger UI) | http://127.0.0.1:8000/docs |
| Alternative API documentation (ReDoc) | http://127.0.0.1:8000/redoc |
| Health check | http://127.0.0.1:8000/health |
| Stored alerts | http://127.0.0.1:8000/alerts |

The API is bound to `127.0.0.1:8000` for local use. PostgreSQL is accessible to the application through Docker's internal network; its port is not published to the host.

## API Reference

### `POST /webhook` — Process an alert

Send a JSON object with the following required fields:

| Field | Type | Description |
| --- | --- | --- |
| `event_id` | string | Unique event identifier (1–128 characters) |
| `source` | string | Alert origin (1–128 characters) |
| `message` | string | Alert description (1–5,000 characters) |
| `timestamp` | ISO 8601 datetime | Event timestamp **with a timezone**, e.g. `2026-11-11T08:00:00Z` |

**Example — macOS / Linux terminal:**

```bash
curl -i -X POST http://127.0.0.1:8000/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id": "evt_98765",
    "source": "server_1",
    "message": "High CPU",
    "timestamp": "2026-11-11T08:00:00Z"
  }'
```

**Example — Windows PowerShell:**

```powershell
$body = @{
    event_id = "evt_98765"
    source   = "server_1"
    message  = "High CPU"
    timestamp = "2026-11-11T08:00:00Z"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/webhook" `
    -Method Post -ContentType "application/json" -Body $body
```

**Example response (`201 Created`):**

```json
{
  "event_id": "evt_98765",
  "source": "server_1",
  "message": "High CPU",
  "timestamp": "2026-11-11T08:00:00Z",
  "processed_at": "2026-11-16T12:00:00Z"
}
```

`processed_at` is generated at processing time; the value above is illustrative. Timestamps are returned in UTC.

For a **new** event, the API waits approximately three seconds before saving and returning it. The delay is non-blocking, so multiple requests can be processed concurrently.

#### Duplicate and invalid requests

| Situation | HTTP status | Result |
| --- | --- | --- |
| New, valid event | `201 Created` | Saves and returns the processed alert |
| Same `event_id` and identical payload | `200 OK` | Returns the existing alert without reprocessing |
| Same `event_id`, different payload | `409 Conflict` | Rejects the conflicting event |
| Missing, invalid, or unexpected fields | `422 Unprocessable Entity` | Returns validation details |
| Database unavailable | `503 Service Unavailable` | Reports a database error |

Event timestamps are normalized to UTC before comparison and storage. The database enforces uniqueness through `event_id`, including during concurrent submissions.

### `GET /alerts` — Retrieve processed alerts

Returns a JSON array of saved alerts, ordered by processing time (newest first).

**macOS / Linux:**

```bash
curl http://127.0.0.1:8000/alerts
```

**Windows PowerShell:**

```powershell
Invoke-RestMethod http://127.0.0.1:8000/alerts
```

If no alerts have been processed, the response is `[]`.

### `GET /health` — Check service health

```bash
curl http://127.0.0.1:8000/health
```

A healthy service returns `200 OK`:

```json
{"status": "ok"}
```

This endpoint checks the database connection, not just whether the API process is running.

## Testing

### End-to-end smoke test (real PostgreSQL)

With the Docker services running, execute:

```bash
python scripts/smoke_test.py
```

The script uses Python's standard library and verifies alert creation, the expected processing delay, duplicate retries, conflicting event IDs, persistence, health checking, parallel requests, and concurrent duplicate submissions. It targets `http://127.0.0.1:8000`.

### Unit tests and linting

Install the development dependencies into your preferred Python 3.12 environment:

```bash
python -m pip install -r requirements-dev.txt
```

Then run:

```bash
python -m pytest -q
ruff check .
```

Unit tests use an in-memory SQLite test database and do not require the Docker stack. The separate smoke test exercises the running API with PostgreSQL.

The included GitHub Actions workflow performs linting, syntax checks, unit tests, and a Docker-based PostgreSQL smoke test on pushes and pull requests.

## Project Structure

```text
.
├── app/
│   ├── config.py              # Environment-based application settings
│   ├── main.py                # API routes and application lifecycle
│   ├── models.py              # SQLAlchemy database model
│   ├── schemas.py             # Request and response validation
│   └── services.py            # Alert processing and duplicate handling
├── alembic/                   # Database migrations
├── alembic.ini                # Alembic configuration
├── scripts/
│   └── smoke_test.py          # End-to-end API checks
├── tests/                     # Unit tests
├── .github/workflows/ci.yml   # Continuous integration
├── .env.example               # Example environment configuration
├── Dockerfile                 # API container image
├── docker-compose.yml         # Local API, migration, and database services
├── docker-compose.prod.yml    # Optional reverse-proxy configuration
├── Caddyfile                  # Optional HTTPS reverse proxy
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Test and lint dependencies
└── README.md
```

## Useful Docker Commands

```bash
# View container status
docker compose ps

# View API logs
docker compose logs -f api

# View database/migration logs
docker compose logs db migrate

# Restart after changing application code
docker compose up -d --build

# Stop the services
docker compose down
```

PostgreSQL data is stored in the named `postgres_data` volume. `docker compose down` retains it. **Do not run `docker compose down -v` unless you intend to permanently delete the local database volume and its alerts.**

## Design Notes

- **Why PostgreSQL?** It provides durable storage and supports database-enforced event uniqueness.
- **Why `asyncio.sleep`?** It simulates a processing delay without occupying a worker thread or blocking other asynchronous requests.
- **Why Alembic?** Database schema changes are managed explicitly and applied before the API starts.
- **Why idempotency?** Webhook senders may retry deliveries; unchanged repeats should not produce duplicate records.

---

