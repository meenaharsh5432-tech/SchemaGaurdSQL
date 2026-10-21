# SchemaGuard SQL

A self-hosted text-to-SQL application built with FastAPI, React, PostgreSQL, and local language models.

Ask a business question in plain English, preview the generated SQL, or execute it through a restricted database connection. Results include a table, a deterministic summary, and execution metadata.

## Features

- React and TypeScript interface for SQL previews and query execution.
- Local SQL generation using Qwen2.5-Coder 3B through Ollama.
- PostgreSQL schema discovery and metadata caching.
- Optional schema retrieval using local EmbeddingGemma embeddings.
- SQLGlot AST validation and an explicit table allowlist.
- Read-only database credentials and transactions.
- EXPLAIN-based estimated cost checks.
- Statement and lock timeouts.
- Maximum of 100 returned rows.
- Up to three SQL repair attempts for selected database errors.
- Redis result caching.
- PostgreSQL audit logging through a separate writer role.
- Custom regression evaluation and a Spider-derived benchmark.
- Docker deployment with an Nginx frontend proxy.
- GitHub Actions for backend tests and frontend builds.

## Architecture

1. The frontend sends a business question to FastAPI.
2. The backend discovers the allowed schema or retrieves relevant tables.
3. A local model generates SQL.
4. The validator checks SQL structure, table access, and row limits.
5. The executor checks estimated cost and executes in a read-only transaction.
6. Selected database errors trigger a bounded repair loop.
7. The API returns rows, SQL, a summary, and request metadata.

Every repaired query passes through validation again.

Repeated questions may be served from Redis. Requests handled by the
`/query` endpoint produce best-effort audit records.

## Technology stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Frontend hosting | Nginx |
| Backend | FastAPI, Pydantic |
| SQL generation | Qwen2.5-Coder 3B through Ollama |
| Schema embeddings | EmbeddingGemma 300M through Ollama |
| Database | PostgreSQL 17 |
| Database access | SQLAlchemy, Psycopg |
| SQL validation | SQLGlot |
| Cache | Redis 7 |
| Testing | Pytest |
| Deployment | Docker Compose |
| CI | GitHub Actions |

## Demonstration database

The seeded business database contains six tables:

- `customers`
- `orders`
- `products`
- `order_items`
- `support_tickets`
- `ticket_messages`

Order amounts are measured in INR. The seeded total order revenue is
**155,000.00 INR**.

`orders.amount` represents order revenue. Historical product sales use
the quantity and unit price stored in `order_items`, rather than a
product's current price.

## Requirements

The project was developed on Windows 11 with:

- Docker Desktop and Docker Compose
- Ollama
- Python 3.14.4 for native backend development and evaluation
- Node.js 24 for native frontend development

The Docker deployment builds Python and frontend dependencies inside
containers. It uses Ollama running on the Windows host.

Commands below use **PowerShell**, except where identified as SQL or
psql commands.

## Clone the repository

```powershell
git clone https://github.com/meenaharsh5432-tech/SchemaGaurdSQL.git
cd SchemaGaurdSQL
```

## Environment configuration

Create `.env` in the project root:

```dotenv
POSTGRES_PASSWORD=replace_with_a_local_admin_password

DATABASE_URL=postgresql+psycopg://sg_reader:sg_reader_local_dev_2026@127.0.0.1:5433/schemaguard
AUDIT_DATABASE_URL=postgresql+psycopg://sg_audit_writer:sg_audit_local_dev_2026@127.0.0.1:5433/schemaguard

DOCKER_DATABASE_URL=postgresql+psycopg://sg_reader:sg_reader_local_dev_2026@postgres:5432/schemaguard
DOCKER_AUDIT_DATABASE_URL=postgresql+psycopg://sg_audit_writer:sg_audit_local_dev_2026@postgres:5432/schemaguard

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:3b

REDIS_URL=redis://127.0.0.1:6380/0
RESULT_CACHE_TTL_SECONDS=60
SCHEMA_RETRIEVAL_ENABLED=false
```

The reader and audit-writer passwords must match the roles created by
the SQL initialization scripts. These sample credentials are intended
for local development.

The deployment Compose file supplies container-specific service
addresses and currently disables schema retrieval.

Do not commit `.env`. Changing its values does not change passwords
on existing PostgreSQL roles.

## Prepare Ollama

Download the SQL model:

```powershell
ollama pull qwen2.5-coder:3b
```

Check whether Ollama is running:

```powershell
curl.exe http://127.0.0.1:11434/api/tags
```

If it is not running, start the Ollama application or run:

```powershell
ollama serve
```

Only one Ollama server should listen on port 11434.

## Docker deployment

This runs PostgreSQL, Redis, FastAPI, and the frontend in containers.
Ollama remains on the Windows host.

### Start

With Docker Desktop and Ollama running:

```powershell
docker compose -f compose.yaml -f compose.deploy.yaml up -d --build --wait postgres redis api frontend
```

Open:

http://127.0.0.1:8080

Nginx serves the built frontend and forwards `/api/` requests to FastAPI.
The API reaches native Ollama through `host.docker.internal:11434`.

On an empty PostgreSQL volume, initialization applies:

1. `database/init.sql`
2. `database/002_audit.sql`
3. `database/003_business_schema.sql`
4. `database/004_business_seed.sql`

Initialization scripts do not rerun on existing volumes.
An existing database must already have the required migrations.

### Verify

```powershell
curl.exe http://127.0.0.1:8080/api/ready
```

Expected response:

```json
{
  "status": "ready",
  "database": "connected",
  "database_user": "sg_reader",
  "read_only": true
}
```

Then ask through the interface:

> What is the total order revenue in INR?

The seeded result should be `155000.00`.

Readiness checks the database connection and selected role
restrictions. It does not verify every dependency, permission,
or audit write.

### Logs

```powershell
docker compose -f compose.yaml -f compose.deploy.yaml logs --tail 100 api frontend
```

### Stop and restart

Stop while preserving database data:

```powershell
docker compose -f compose.yaml -f compose.deploy.yaml stop
```

Restart:

```powershell
docker compose -f compose.yaml -f compose.deploy.yaml up -d --wait postgres redis api frontend
```

Keep Ollama running when submitting questions.

The base configuration publishes PostgreSQL on localhost port 5433
and Redis on localhost port 6380. The deployment frontend uses port
8080. Avoid starting another project that uses the same ports.

## Native development

In this setup, PostgreSQL and Redis run in Docker while FastAPI,
Vite, and Ollama run on the host.

### 1. Install Python dependencies

From the project root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Start PostgreSQL and Redis

```powershell
docker compose up -d --wait postgres redis
```

On a fresh volume, the base Compose file automatically runs
`database/init.sql`.

Apply the additional migrations once:

```powershell
docker compose cp database/002_audit.sql postgres:/tmp/002_audit.sql
docker compose exec postgres psql -h 127.0.0.1 -U sg_admin -d schemaguard -W -v ON_ERROR_STOP=1 -f /tmp/002_audit.sql

docker compose cp database/003_business_schema.sql postgres:/tmp/003_business_schema.sql
docker compose exec postgres psql -h 127.0.0.1 -U sg_admin -d schemaguard -W -v ON_ERROR_STOP=1 -f /tmp/003_business_schema.sql

docker compose cp database/004_business_seed.sql postgres:/tmp/004_business_seed.sql
docker compose exec postgres psql -h 127.0.0.1 -U sg_admin -d schemaguard -W -v ON_ERROR_STOP=1 -f /tmp/004_business_seed.sql
```

Enter the admin password configured in `.env`.

Do not rerun these migrations on an initialized database, including
one initialized through the Docker deployment configuration.

### 3. Start FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

- API documentation: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/health
- Database readiness: http://127.0.0.1:8000/ready

### 4. Start React

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite.

The development proxy forwards `/api/query` to the backend's `/query`
endpoint on port 8000.

### Stop native development

Stop FastAPI and Vite with Ctrl+C in their terminals.

Stop PostgreSQL and Redis:

```powershell
docker compose stop postgres redis
```

This preserves the PostgreSQL volume.

## Using the application

**Generate SQL** previews a validated query without executing it.

**Run query** submits the question for execution and returns rows,
SQL, a summary, and request metadata.

The execution endpoint generates SQL from the question. It does not
guarantee execution of exactly the SQL shown in an earlier preview.

Example questions:

- What is the total order revenue in INR?
- Which customers have spent more than 50000 INR in total?
- List customers who have never placed an order.
- List customer IDs and names ordered by customer ID.
- List high priority open support tickets.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API liveness |
| GET | `/ready` | Database readiness and selected role checks |
| POST | `/generate-sql` | Generate and validate SQL |
| POST | `/query` | Generate, validate, execute or retrieve cached results |

Both POST endpoints accept:

```json
{
  "question": "What is the total order revenue in INR?"
}
```

When accessing the packaged frontend, prefix these paths with `/api`.

A cached response returns `cache_hit: true` and `executed: false`.
This means the result SQL was not executed again for that request.

Handled `/query` responses include request and audit-status headers.
Audit logging is best effort; query success alone does not prove that
an audit record was saved.

## Optional schema retrieval

Schema retrieval combines:

- Local table-metadata embeddings.
- Cosine-similarity ranking.
- Explicit table mentions.
- Foreign-key paths connecting selected tables.

Download the embedding model:

```powershell
ollama pull embeddinggemma:300m
```

For native execution, enable retrieval before starting the backend or
evaluation process:

```powershell
$env:SCHEMA_RETRIEVAL_ENABLED = "true"
```

Remove the temporary override afterward:

```powershell
Remove-Item Env:SCHEMA_RETRIEVAL_ENABLED -ErrorAction SilentlyContinue
```

For the containerized API, change `SCHEMA_RETRIEVAL_ENABLED` in
`compose.deploy.yaml` and recreate the API container.

Retrieval is disabled by default. On this small demonstration schema,
embedding requests added overhead without improving the latest
regression accuracy.

Reference-table coverage passed all 18 custom evaluation questions.
Coverage indicates that required reference tables were selected;
it does not guarantee correct SQL generation.

## Testing

Start PostgreSQL and Redis with the required schema initialized.

From the project root:

```powershell
Remove-Item Env:RUN_LIVE_LLM_TESTS -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q
```

The live Ollama repair test is opt-in:

```powershell
$env:RUN_LIVE_LLM_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_live_repair.py -q -s
Remove-Item Env:RUN_LIVE_LLM_TESTS
```

Build the frontend:

```powershell
cd frontend
npm ci
npm run build
```

GitHub Actions runs backend tests and the frontend build.
Live model benchmarks and browser interaction tests are not
currently executed in CI.

## Custom evaluation

With PostgreSQL and Ollama running, execute from the project root:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_eval --cases cases.json
.\.venv\Scripts\python.exe -m evaluation.run_eval --cases holdout_cases.json
.\.venv\Scripts\python.exe -m evaluation.run_eval --cases expanded_cases.json
```

The evaluator:

- Compares returned values with reference-query results.
- Preserves duplicate-row counts.
- Checks ordering when required.
- Ignores differences in column aliases.
- Bypasses Redis result caching.
- Records accuracy, repair attempts, and workflow latency.
- Saves model, prompt, policy, and case configuration.
- Exits with a nonzero status when a case fails.

The latest reported development runs matched **18/18 custom cases**
without repairs, both with full schema and with retrieval enabled.

These cases were used during development and prompt refinement.
The file named `holdout_cases.json` is now a regression set.

These results are not a general accuracy estimate. With six
questions per suite, nearest-rank p95 is the slowest measured request.
Model loading and other runtime conditions can affect latency.

## Spider-derived evaluation

A separate evaluation adapts the Spider 1.0 `poker_player`
development database to PostgreSQL.

It uses a dedicated database and read-only role. It does not replace
or add benchmark tables to the application's business database.

### Reported results

| Measurement | Result |
|---|---|
| Reference-result parity after adaptation | 40/40 |
| Structurally supported reference cases | 38/40 |
| Baseline correct supported cases | 35/38 — 92.11% |
| Revised repair configuration | 36/38 — 94.74% |
| Revised first-attempt accuracy | 34/38 — 89.47% |
| Revised repair success | 2/3 attempted repairs |

Two reference queries containing unsupported subqueries were
excluded from model evaluation.

This is a PostgreSQL-adapted evaluation on one Spider development
database. It is not an official full Spider benchmark score or an
unseen test-set result. Repair instructions were refined after
inspecting failures.

### Prepare the dataset

Download Spider 1.0 from:

https://yale-lily.github.io/spider

Extract it so these paths exist:

- `evaluation/data/spider/dev.json`
- `evaluation/data/spider/tables.json`
- `evaluation/data/spider/database/`

Downloaded data and generated reports are excluded from Git.

### Create the benchmark database

Start PostgreSQL:

```powershell
docker compose up -d --wait postgres
```

Connect as administrator:

```powershell
docker compose exec postgres psql -h 127.0.0.1 -U sg_admin -d postgres -W
```

Run:

```sql
CREATE DATABASE schemaguard_spider
    OWNER sg_admin
    TEMPLATE template0
    ENCODING 'UTF8'
    LC_COLLATE 'C'
    LC_CTYPE 'C';

REVOKE ALL ON DATABASE schemaguard_spider FROM PUBLIC;
```

Enter this psql command on its own line:

```text
\connect schemaguard_spider sg_admin
```

After connecting:

```sql
REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

Exit using `\q` on its own line.

### Import and verify

Install the Python dependencies described in Native development,
then run:

```powershell
.\.venv\Scripts\python.exe -m evaluation.import_spider_poker
```

The importer prompts for the admin password and a new
`sg_spider_reader` password. It refuses to overwrite existing tables
or reuse an existing benchmark-reader role.

Verify reference-query parity:

```powershell
.\.venv\Scripts\python.exe -m evaluation.verify_spider_poker
```

All 40 reference cases should pass before model evaluation.

### Run model evaluation

With Ollama running and `qwen2.5-coder:3b` available:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_spider_poker
```

Enter the benchmark-reader password when prompted.

The report is saved to:

`evaluation/spider_poker_model_report.json`

A nonzero exit status indicates that at least one evaluated case
failed. The completed report is still saved.

For subsequent runs, reuse the existing benchmark database and role.
Do not repeat database creation or import.

The current runner uses revised column-ownership repair instructions.
Its results should not be described as reproducing the earlier
unmodified baseline.

## Safety and privacy boundaries

Prompt instructions alone are not a security boundary.

The application combines:

- Single-statement SELECT validation.
- An explicit AST-node allowlist.
- Schema-qualified, allowlisted tables.
- Restricted database credentials.
- Read-only transactions.
- EXPLAIN-based cost rejection.
- Statement and lock timeouts.
- A returned-row cap.

EXPLAIN costs are estimates rather than guaranteed resource bounds.
A query can pass every structural check and still answer the wrong
business question.

During inference, prompts and schema metadata go to the configured
Ollama endpoint. The documented setup uses a local model service.
Downloading dependencies and models requires network access.

Redis contains cached results. Audit records can contain question
text and SQL. These stores must be included in deployment privacy
and retention decisions.

## Current limitations

- The application demonstrates a fixed, allowlisted business schema.
- SQL support is intentionally narrow: CTEs, subqueries, unions, and
  many functions are rejected.
- Repair handles selected database errors, not every validation
  failure or semantic mistake.
- Explanations are deterministic summaries.
- Cached results can be stale until their TTL expires.
- Audit logging is best effort and records request summaries rather
  than every generation attempt.
- Requests rejected before the endpoint handler may not be audited.
- Authentication, per-user authorization, and rate limiting are not
  implemented.
- Live model evaluation is manual.
- Spider evaluation covers one adapted development database.
- Docker deployment has been exercised on Windows with native Ollama;
  other host environments may require configuration changes.

This project is a local portfolio application. Public or multi-user
deployment requires additional access controls and operational work.