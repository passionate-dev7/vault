-- VAULT schema  — catalog-scale QC archive triage.
--
-- The ClickHouse story in one sentence: ffmpeg's ebur128 filter emits a reading
-- every 100ms, so one 90-minute feature produces ~54,000 loudness rows.
-- A 30-title catalog produces ~1.6M rows in the first 2 minutes of each film alone.
-- Catalog questions ("which titles fail", "worst 60s window", "cheapest to rescue")
-- are analytical scans over that — exactly what ClickHouse is for.

CREATE DATABASE IF NOT EXISTS vault;

-- Per-100ms loudness time series. THE high-volume table.
-- One 2-minute excerpt = ~1,200 rows; 30 titles = ~36,000+ rows minimum.
CREATE TABLE IF NOT EXISTS vault.loudness_samples
(
    title_id   String,
    scanned_at DateTime DEFAULT now(),
    t_seconds  Float32,
    momentary  Float32,     -- M: 400ms window
    short_term Float32,     -- S: 3s window
    integrated Float32,     -- I: cumulative from start of scan
    true_peak  Float32      -- FTPK in dBFS
)
ENGINE = MergeTree
ORDER BY (title_id, t_seconds)
PARTITION BY toYYYYMM(scanned_at);

-- One row per spec-check per title scan.
CREATE TABLE IF NOT EXISTS vault.findings
(
    title_id     String,
    title        String,
    scanned_at   DateTime DEFAULT now(),
    check_name   LowCardinality(String),
    spec         LowCardinality(String),
    measured     Nullable(Float64),
    target       Nullable(Float64),
    unit         LowCardinality(String),
    passed       UInt8,
    auto_fixable UInt8,
    rescue_cost  String,   -- plain-English cost estimate e.g. "loudnorm pass, ~2min/title"
    detail       String
)
ENGINE = MergeTree
ORDER BY (title_id, check_name, scanned_at);

-- Catalog-level summary view — latest run per title only.
-- argMax(scanned_at) avoids double-counting when a title is re-scanned.
CREATE OR REPLACE VIEW vault.catalog_summary AS
SELECT
    title_id,
    any(title)                                                    AS title,
    max(scanned_at)                                               AS last_scanned,
    count() FILTER (WHERE passed=0)                               AS failures,
    count() FILTER (WHERE passed=1)                               AS passes,
    count() FILTER (WHERE fixable=1 AND failed=1)                 AS auto_fixable,
    count() FILTER (WHERE fixable=0 AND failed=1)                 AS needs_human,
    multiIf(count() FILTER (WHERE passed=0) = 0, 'PASS', 'FAIL') AS verdict,
    groupArray(if(failed=1, check_name, ''))                      AS failed_checks,
    groupArray(if(failed=1, rescue_cost, ''))                     AS rescue_costs
FROM (
    SELECT f.*,
           (1 - f.passed)       AS failed,
           f.auto_fixable       AS fixable
    FROM vault.findings f
    WHERE (f.title_id, f.scanned_at) IN (
        SELECT title_id, max(scanned_at) FROM vault.findings GROUP BY title_id
    )
)
GROUP BY title_id
ORDER BY failures DESC;

-- Worst sustained loudness window per title (what an operator listens to first).
CREATE OR REPLACE VIEW vault.loudness_extremes AS
SELECT
    title_id,
    round(min(integrated), 1)                     AS integrated_lufs,
    round(min(short_term), 1)                     AS worst_short_term_lufs,
    round(max(short_term), 1)                     AS best_short_term_lufs,
    round(max(true_peak), 1)                      AS max_true_peak_dbfs,
    argMin(t_seconds, short_term)                 AS worst_window_at_seconds,
    count()                                       AS sample_count
FROM vault.loudness_samples
WHERE short_term > -70   -- exclude uninitialised/silent periods
GROUP BY title_id;
