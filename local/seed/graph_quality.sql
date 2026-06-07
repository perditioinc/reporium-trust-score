-- Local OSS seed for the graph-quality metrics the trust-score Quality
-- sub-score reads. This stands in for the production Postgres that backs
-- /metrics/graph-quality (source: "postgres_live").
--
-- Each row is one edge family. The stub (local/stub/app.py) SELECTs these
-- rows and shapes them into the /metrics/graph-quality contract. Values are
-- chosen so every family is above the KAN-147 precision floor (0.7) and has
-- live edges, yielding a healthy, nonzero Quality sub-score through
-- lib/score.py:quality_subscore.

CREATE TABLE IF NOT EXISTS graph_quality_edge_types (
    edge_type           TEXT PRIMARY KEY,
    live_edges          INTEGER NOT NULL DEFAULT 0,
    precision_proxy     DOUBLE PRECISION,
    recall_proxy        DOUBLE PRECISION,
    eligible_repos      INTEGER NOT NULL DEFAULT 0,
    observed_repos      INTEGER NOT NULL DEFAULT 0,
    invalid_live_edges  INTEGER NOT NULL DEFAULT 0
);

TRUNCATE graph_quality_edge_types;

-- DEPENDS_ON: exact precision/recall in production. precision_proxy column
-- carries the exact precision here; the stub maps it to "precision".
INSERT INTO graph_quality_edge_types
    (edge_type, live_edges, precision_proxy, recall_proxy, eligible_repos, observed_repos, invalid_live_edges)
VALUES
    ('DEPENDS_ON',      250, 1.00, 1.00,  250,  250,    0),
    ('ALTERNATIVE_TO',  120, 0.95, 1.00, 1912, 1912, 1335),
    ('EXTENDS',          40, 0.90, 0.50, 1921,  525,    0),
    ('COMPATIBLE_WITH',  60, 0.85, 0.40,  300,  300,    0);
