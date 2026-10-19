# SchemaGuard SQL

A self-hosted text-to-SQL application that answers business questions using a local language model and a read-only PostgreSQL connection.

SchemaGuard generates SQL, validates it, checks estimated query cost, executes it with limits, and returns a table with a short deterministic summary.

## Features

- React and TypeScript interface for SQL previews and query execution.
- Local SQL generation with Qwen2.5-Coder through Ollama.
- PostgreSQL schema discovery with an in-process metadata cache.
- SQLGlot-based structural validation and a table allowlist.
- Read-only database role and read-only transactions.
- EXPLAIN-based estimated cost checks.
- Statement timeout, lock timeout, and a maximum of 100 returned rows.
- Up to three repair attempts for selected database errors.
- Redis result caching.
- PostgreSQL audit records for handled `/query` requests.
- A curated execution-result evaluation harness.
- GitHub Actions for backend tests and the frontend build.

## Architecture

The React frontend sends questions to FastAPI. The backend supplies allowed schema metadata to the local model, validates the generated SQL, and executes it through a restricted database connection.

Selected database errors trigger a repair attempt. Every repaired query passes through validation again.

Repeated questions can be served from Redis. Successful and failed requests handled by the `/query` endpoint are recorded through a separate audit-writer connection.

## Stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| API | FastAPI, Pydantic |
| Local inference | Ollama, Qwen2.5-Coder 3B |
| Database access | SQLAlchemy, Psycopg |
| Database | PostgreSQL 17 |
| SQL validation | SQLGlot |
| Result cache | Redis 7 |
| Tests | Pytest |
| CI | GitHub Actions |

## Requirements

The project was developed with:

- Windows 11
- Python 3.14.4
- Node.js 24
- Docker Desktop with Docker Compose
- Ollama with `qwen2.5-coder:3b`

PostgreSQL and Redis run in Docker. FastAPI, React's development server, and Ollama run on the host.

## Local setup

The following commands use Windows Command Prompt.

### 1. Clone the repository

```bat
git clone https://github.com/meenaharsh5432-tech/SchemaGaurdSQL.git
cd SchemaGaurdSQL
```

### 2. Install Python dependencies

```bat
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Configure the environment

Create a `.env` file in the project root:

```dotenv
POSTGRES_PASSWORD=replace_with_a_local_admin_password
DATABASE_URL=postgresql+psycopg://sg_reader:sg_reader_local_dev_2026@127.0.0.1:5433/schemaguard
AUDIT_DATABASE_URL=postgresql+psycopg://sg_audit_writer:sg_audit_local_dev_2026@127.0.0.1:5433/schemaguard
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b
REDIS_URL=redis://127.0.0.1:6380/0
RESULT_CACHE_TTL_SECONDS=60
```

The reader and audit-writer credentials must match the development roles created by the SQL initialization scripts. These sample credentials are for disposable local development only.

Do not commit `.env`.

### 4. Start PostgreSQL and Redis

Open Docker Desktop, then run:

```bat
docker compose up -d --wait postgres redis
```

On a fresh PostgreSQL volume, Compose automatically applies `database/init.sql`, creating the business schema, sample data, and reader role.

Apply the audit migration once for that database:

```bat
docker compose cp database/002_audit.sql postgres:/tmp/002_audit.sql
docker compose exec postgres psql -h 127.0.0.1 -U sg_admin -d schemaguard -W -v ON_ERROR_STOP=1 -f /tmp/002_audit.sql
```

Enter the admin password configured in `.env`.

Initialization scripts do not automatically rerun on an existing database volume. Changing a password in `.env` does not change an existing database role's password.

### 5. Prepare Ollama

```bat
ollama pull qwen2.5-coder:3b
```

If Ollama is not already running:

```bat
ollama serve
```

Only one Ollama server should listen on port 11434.

### 6. Start FastAPI

In a separate terminal, from the project root:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

- API documentation: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/health
- Database readiness: http://127.0.0.1:8000/ready

The readiness endpoint checks the database connection and selected role restrictions. It does not verify every dependency or permission.

### 7. Start React

In another terminal:

```bat
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite.

The frontend must point to the FastAPI server on port 8000. With the Vite development proxy, `/api/query` forwards to `/query`.

The development proxy is not a production hosting configuration.

## Using the application

**Generate SQL** previews a validated query without executing it.

**Run query** submits the business question for execution and returns rows, SQL, a summary, and request metadata. The query endpoint generates SQL from the question; it does not guarantee execution of exactly the SQL shown in an earlier preview.

Example questions:

- What is the total order revenue in INR?
- Which customers have spent more than 50000 INR in total?
- List customers who have never placed an order.
- List customer IDs and names ordered by customer ID.

With the original sample data, total order revenue is INR 155,000.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API liveness |
| GET | `/ready` | Database readiness and selected role checks |
| POST | `/generate-sql` | Generate and validate SQL without execution |
| POST | `/query` | Generate, validate, execute or retrieve a cached result |

Both POST endpoints accept:

```json
{
  "question": "What is the total order revenue in INR?"
}
```

A cache hit returns `cache_hit: true` and `executed: false`, indicating that the result SQL was not executed again for that request.

## Testing

Start PostgreSQL and Redis before running the backend suite.

From Windows Command Prompt:

```bat
set RUN_LIVE_LLM_TESTS=
.venv\Scripts\python.exe -m pytest -q
```

The last reported local run completed with **48 passed and 1 skipped**. The skipped test requires live Ollama inference.

To run the opt-in live repair test:

```bat
set RUN_LIVE_LLM_TESTS=1
.venv\Scripts\python.exe -m pytest tests/test_live_repair.py -q -s
set RUN_LIVE_LLM_TESTS=
```

Build the frontend:

```bat
cd frontend
npm run build
```

GitHub Actions runs backend tests and the frontend build. It does not currently run live model evaluation or browser interaction tests.

## Evaluation

From the project root, with PostgreSQL and Ollama running:

```bat
.venv\Scripts\python.exe -m evaluation.run_eval --cases cases.json
.venv\Scripts\python.exe -m evaluation.run_eval --cases holdout_cases.json
```

The evaluator:

- Compares returned values against reference-query results.
- Preserves duplicate-row counts.
- Checks row ordering when required.
- Ignores differences in column aliases.
- Bypasses Redis result caching by calling the workflow directly.
- Records accuracy, repair attempts, and workflow latency.
- Saves JSON reports with model, policy, prompt, and case identifiers.
- Exits with a nonzero code when a case fails.

The latest reported development runs matched **12 of 12 cases on the sample database**, without repairs.

Both case files are now regression sets: their results were used to refine the prompt, including the file named `holdout_cases.json`.

These results are not a Spider benchmark, a general accuracy estimate, or proof of correctness on other databases. With only six questions per suite, nearest-rank p95 is the slowest measured request.

## Safety and privacy boundaries

SQL validation, restricted privileges, and execution limits provide independent protections. Prompt instructions alone are not a security boundary.

Current restrictions include:

- One SELECT statement using an explicit AST allowlist.
- Access limited to approved business tables.
- Restricted database credentials.
- Read-only transactions.
- Estimated cost rejection and execution timeouts.
- A returned-row cap.

EXPLAIN costs are estimates, not guaranteed resource bounds. A structurally valid query can still answer the wrong business question.

Inference uses the configured local Ollama endpoint. Result data is stored in Redis, and audit records may contain question text and SQL. Deployments must account for those local data stores.

## Current limitations

- The demonstration schema contains two business tables.
- Schema metadata is discovered and cached; embedding-based table retrieval is not implemented.
- SQL support is intentionally narrow: CTEs, subqueries, unions, and many functions are rejected.
- Repair targets selected database errors, not all semantic mistakes.
- Explanations are deterministic result summaries.
- Cached results can be stale until their TTL expires.
- Audit logging is best effort and records request summaries rather than every generation attempt.
- Requests rejected before the endpoint handler may not be audited.
- Authentication, per-user authorization, and rate limiting are not implemented.
- CI does not yet run Spider evaluation or live LLM benchmarks.
- The current setup is a local development application, not a production deployment.

## Stopping local services

Stop FastAPI and Vite with Ctrl+C in their terminals.

Stop database and cache containers with:

```bat
docker compose stop postgres redis
```

This preserves the PostgreSQL volume. Removing the volume deletes the stored database.