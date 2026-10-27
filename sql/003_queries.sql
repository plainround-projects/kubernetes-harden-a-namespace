-- The statements the service runs, each with a line on what it shows. Run them with `make db-queries`.

-- Record a visit: create the page's row on first use, otherwise add one. This is the service's only write.
INSERT INTO visits (page, visit_count) VALUES ('/', 1)
ON CONFLICT (page) DO UPDATE SET visit_count = visits.visit_count + 1, last_visit_at = now()
RETURNING visit_count;

-- Readiness: the cheapest statement that proves the database accepts this user's connection and answers.
SELECT 1;

-- Look at the counters: what the team's service has served so far.
SELECT page, visit_count, last_visit_at FROM visits ORDER BY page;
