-- DDL for a team's database. Idempotent: the Postgres image runs it from /docker-entrypoint-initdb.d on first
-- start, and `make db` can run it again against a running database.

CREATE TABLE IF NOT EXISTS visits (
    page          text        PRIMARY KEY,
    visit_count   bigint      NOT NULL DEFAULT 0 CONSTRAINT visits_count_not_negative CHECK (visit_count >= 0),
    last_visit_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  visits               IS 'One row per page the team''s web service has served; the service increments visit_count.';
COMMENT ON COLUMN visits.page          IS 'The request path, for example /.';
COMMENT ON COLUMN visits.visit_count   IS 'Visits since the row was created. Only ever increased by the service.';
COMMENT ON COLUMN visits.last_visit_at IS 'When the service last counted a visit to this page.';
