BEGIN;

CREATE SCHEMA audit AUTHORIZATION sg_admin;

REVOKE ALL ON SCHEMA audit FROM PUBLIC;

CREATE TABLE audit.query_events (
    request_id UUID PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    endpoint TEXT NOT NULL,
    question TEXT,
    generated_sql TEXT,

    status TEXT NOT NULL
        CHECK (status IN ('success', 'failure')),

    http_status SMALLINT NOT NULL
        CHECK (http_status BETWEEN 100 AND 599),

    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    executed BOOLEAN NOT NULL DEFAULT FALSE,

    repair_count SMALLINT
        CHECK (repair_count BETWEEN 0 AND 3),

    row_count INTEGER
        CHECK (row_count >= 0),

    total_duration_ms DOUBLE PRECISION NOT NULL
        CHECK (total_duration_ms >= 0),

    database_duration_ms DOUBLE PRECISION
        CHECK (database_duration_ms >= 0),

    schema_version TEXT,
    model TEXT,
    error_code TEXT,

    CHECK (NOT (cache_hit AND executed))
);

CREATE INDEX query_events_recorded_at_idx
    ON audit.query_events (recorded_at DESC);

CREATE ROLE sg_audit_writer
    LOGIN
    PASSWORD 'sg_audit_local_dev_2026'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT CONNECT ON DATABASE schemaguard TO sg_audit_writer;

GRANT USAGE ON SCHEMA audit TO sg_audit_writer;

REVOKE ALL ON TABLE audit.query_events FROM PUBLIC;
GRANT INSERT ON TABLE audit.query_events TO sg_audit_writer;

ALTER ROLE sg_audit_writer IN DATABASE schemaguard
    SET statement_timeout = '3s';

ALTER ROLE sg_audit_writer IN DATABASE schemaguard
    SET lock_timeout = '1s';

ALTER ROLE sg_audit_writer IN DATABASE schemaguard
    SET search_path = pg_catalog;

COMMIT;