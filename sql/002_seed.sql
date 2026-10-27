-- DML: the starting data. The home page exists with zero visits, so the first request returns 1.
-- Idempotent: running it again changes nothing.

INSERT INTO visits (page, visit_count)
VALUES ('/', 0)
ON CONFLICT (page) DO NOTHING;
