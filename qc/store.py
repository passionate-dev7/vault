"""ClickHouse store for VAULT QC telemetry.

Connects to the local ClickHouse instance (binary /tmp/clickhouse, HTTP 8123, native 9000).
Uses clickhouse-connect for direct inserts; the AGENT queries through mcp-clickhouse MCP.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import clickhouse_connect

# Per-100ms ebur128 sample regex matching ffmpeg's per-frame log line.
_SAMPLE = re.compile(
    r"t:\s*([\d.]+)\s+TARGET:\s*-?\d+\s*LUFS\s+"
    r"M:\s*(-?[\d.inf]+)\s+S:\s*(-?[\d.inf]+)\s+"
    r"I:\s*(-?[\d.inf]+)\s*LUFS\s+LRA:\s*(-?[\d.inf]+)\s*LU"
    r"(?:\s+FTPK:\s*(-?[\d.inf]+))?"
)


def _f(raw: str | None) -> float:
    if raw is None:
        return -120.0
    if "inf" in str(raw):
        return -120.0
    try:
        return float(raw)
    except ValueError:
        return -120.0


def client() -> clickhouse_connect.driver.Client:
    """Return a ClickHouse client from env / defaults."""
    host     = os.getenv("CLICKHOUSE_HOST", "localhost")
    secure   = os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true"
    port     = int(os.getenv("CLICKHOUSE_PORT", "8443" if secure else "8123"))
    return clickhouse_connect.get_client(
        host=host, port=port,
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        secure=secure,
    )


def apply_schema(ch=None) -> None:
    ch = ch or client()
    sql = (Path(__file__).parent.parent / "schema.sql").read_text()
    # Strip comments before splitting to avoid empty-statement errors
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    clean_sql = "\n".join(lines)
    for stmt in [s.strip() for s in clean_sql.split(";") if s.strip()]:
        ch.command(stmt)


def loudness_timeseries(path: str | Path, seconds: int | None = None) -> list[tuple]:
    """Parse every 100ms ebur128 reading from ffmpeg stderr.

    This is the table that justifies ClickHouse: ~10 rows/second of content.
    A 2-minute excerpt = ~1,200 rows; a 30-title catalog scan = ~36,000+ rows.
    """
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path)]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-af", "ebur128=peak=true", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    rows: list[tuple] = []
    for m in _SAMPLE.finditer(proc.stderr):
        rows.append((
            float(m.group(1)),  # t_seconds
            _f(m.group(2)),     # momentary (M)
            _f(m.group(3)),     # short_term (S)
            _f(m.group(4)),     # integrated (I)
            _f(m.group(6)),     # true_peak (FTPK)
        ))
    return rows


def store_findings(title_id: str, title: str, report, ch=None) -> None:
    """Insert all findings from a QCReport into vault.findings."""
    ch = ch or client()
    if not report.findings:
        return
    ch.insert(
        "vault.findings",
        [
            [
                title_id, title, f.check, f.spec,
                f.measured, f.target, f.unit,
                1 if f.passed else 0,
                1 if f.auto_fixable else 0,
                f.rescue_cost, f.detail,
            ]
            for f in report.findings
        ],
        column_names=[
            "title_id", "title", "check_name", "spec",
            "measured", "target", "unit",
            "passed", "auto_fixable", "rescue_cost", "detail",
        ],
    )


def store_samples(title_id: str, samples: list[tuple], ch=None) -> int:
    """Insert loudness time series. Returns row count inserted."""
    ch = ch or client()
    if not samples:
        return 0
    ch.insert(
        "vault.loudness_samples",
        [[title_id, t, mo, st, i, tp] for t, mo, st, i, tp in samples],
        column_names=["title_id", "t_seconds", "momentary", "short_term", "integrated", "true_peak"],
    )
    return len(samples)


def row_count(table: str = "vault.loudness_samples", ch=None) -> int:
    ch = ch or client()
    res = ch.query(f"SELECT count() FROM {table}")
    return res.result_rows[0][0]


def catalog_summary(ch=None) -> list[dict]:
    """Pull the catalog view — asserts non-empty before returning."""
    ch = ch or client()
    res = ch.query(
        "SELECT title_id, title, last_scanned, failures, passes, "
        "auto_fixable, needs_human, verdict, failed_checks, rescue_costs "
        "FROM vault.catalog_summary"
    )
    rows = [dict(zip(res.column_names, row)) for row in res.result_rows]
    if not rows:
        raise RuntimeError("vault.catalog_summary is empty — run ingest first")
    return rows


def loudness_extremes(ch=None) -> list[dict]:
    ch = ch or client()
    res = ch.query(
        "SELECT title_id, integrated_lufs, worst_short_term_lufs, "
        "best_short_term_lufs, max_true_peak_dbfs, worst_window_at_seconds, sample_count "
        "FROM vault.loudness_extremes ORDER BY integrated_lufs ASC"
    )
    return [dict(zip(res.column_names, row)) for row in res.result_rows]


def worst_window(title_id: str, ch=None) -> dict | None:
    """Quietest sustained short-term window for one title, or None if unmeasured."""
    ch = ch or client()
    res = ch.query(
        "SELECT worst_window_at_seconds, worst_short_term_lufs, best_short_term_lufs "
        "FROM vault.loudness_extremes WHERE title_id = %(t)s",
        parameters={"t": title_id},
    )
    if not res.result_rows:
        return None
    at, quietest, loudest = res.result_rows[0]
    return {
        "quietest_at_seconds": float(at),
        "quietest_short_term_lufs": float(quietest),
        "loudest_short_term_lufs": float(loudest),
    }
