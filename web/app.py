"""Redslip web UI: FastAPI single-page rejection ledger.

Endpoints:
  GET  /           — catalog table (sortable, per-title drill-down)
  GET  /api/catalog — raw catalog JSON
  GET  /api/title/{id} — per-title findings + loudness extremes
  GET  /api/stats   — row counts and headline numbers
  POST /api/triage  — trigger Gemini rescue plan via MCP
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder

from qc import store

log = logging.getLogger(__name__)

app = FastAPI(title="Redslip", docs_url=None, redoc_url=None)


def _ch():
    return store.client()


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (Path(__file__).with_name("index.html")).read_text()
    return HTMLResponse(html)


@app.get("/api/stats")
async def stats():
    try:
        ch = _ch()
        loudness_rows = store.row_count("vault.loudness_samples", ch=ch)
        finding_rows  = store.row_count("vault.findings", ch=ch)

        title_count   = ch.query(
            "SELECT count(DISTINCT title_id) FROM vault.findings"
        ).result_rows[0][0]

        fail_count    = ch.query(
            "SELECT count() FROM vault.catalog_summary WHERE verdict = 'FAIL'"
        ).result_rows[0][0]

        pass_count    = ch.query(
            "SELECT count() FROM vault.catalog_summary WHERE verdict = 'PASS'"
        ).result_rows[0][0]

        auto_fix      = ch.query(
            "SELECT count() FROM vault.catalog_summary WHERE needs_human = 0 AND failures > 0"
        ).result_rows[0][0]

        return {
            "loudness_sample_rows": loudness_rows,
            "finding_rows":         finding_rows,
            "title_count":          title_count,
            "failing":              fail_count,
            "passing":              pass_count,
            "auto_fixable":         auto_fix,
            "scan_window_seconds":  120,
            "scan_window_label":    "first 2 minutes of each title",
            "ebu_r128_target_lufs": -23.0,
            "note": (
                f"ebur128 emits ~10 rows/sec; {loudness_rows:,} rows across "
                f"{title_count} titles. Full 28,423-title catalog would produce ~27M rows."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/catalog")
async def catalog():
    try:
        rows = store.catalog_summary()
        extremes = {e["title_id"]: e for e in store.loudness_extremes()}
        for row in rows:
            tid = row["title_id"]
            if tid in extremes:
                ex = extremes[tid]
                row["integrated_lufs"]        = ex["integrated_lufs"]
                row["worst_short_term_lufs"]  = ex["worst_short_term_lufs"]
                row["max_true_peak_dbfs"]      = ex["max_true_peak_dbfs"]
                row["worst_window_seconds"]    = ex["worst_window_at_seconds"]
                row["loudness_sample_count"]   = ex["sample_count"]
        # Clean up array fields for JSON
        for row in rows:
            row["failed_checks"]  = [c for c in (row.get("failed_checks") or []) if c]
            row["rescue_costs"]   = [c for c in (row.get("rescue_costs")  or []) if c]
            # Serialize datetime
            if hasattr(row.get("last_scanned"), "isoformat"):
                row["last_scanned"] = row["last_scanned"].isoformat()
        return JSONResponse(jsonable_encoder(rows))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/title/{title_id:path}")
async def title_detail(title_id: str):
    try:
        ch = _ch()
        res = ch.query(
            "SELECT check_name, spec, measured, target, unit, passed, auto_fixable, "
            "rescue_cost, detail "
            "FROM vault.findings "
            "WHERE title_id = %(t)s "
            "ORDER BY passed ASC, check_name",
            parameters={"t": title_id},
        )
        findings = [dict(zip(res.column_names, row)) for row in res.result_rows]
        # Silent audio measures true_peak = -inf, which is not valid JSON.
        # Keep the finding, drop the unencodable number.
        for f in findings:
            for k, v in f.items():
                if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                    f[k] = None
        if not findings:
            raise HTTPException(status_code=404, detail=f"No findings for {title_id!r}")

        # Loudness time series (sampled for chart: every 10th row)
        ts_res = ch.query(
            "SELECT t_seconds, short_term, integrated FROM vault.loudness_samples "
            "WHERE title_id = %(t)s ORDER BY t_seconds",
            parameters={"t": title_id},
        )
        ts_rows = ts_res.result_rows
        # Downsample for the chart
        step = max(1, len(ts_rows) // 300)
        chart = [
            {"t": round(r[0], 1), "st": round(r[1], 1), "i": round(r[2], 1)}
            for r in ts_rows[::step]
        ]

        return {
            "title_id": title_id,
            "findings": findings,
            "loudness_chart": chart,
            "sample_count": len(ts_rows),
            # Quietest sustained passage, so the slip can point a mixer at a
            # timestamp instead of at the plot. None when nothing was measured.
            "worst_window": store.worst_window(title_id, ch=ch),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/triage")
async def triage():
    """Run Gemini triage via MCP. May take 30-60s on first call."""
    try:
        from agent.triage import run_triage
        result = await asyncio.get_event_loop().run_in_executor(None, run_triage)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/mcp-log")
async def mcp_log():
    """Return the last 50 MCP tool calls (proof of MCP usage)."""
    log_file = Path(__file__).parent.parent / "logs" / "mcp_tool_calls.jsonl"
    if not log_file.exists():
        return {"entries": [], "note": "No MCP calls logged yet. Run /api/triage first."}
    lines = log_file.read_text().strip().splitlines()
    entries = []
    for line in lines[-50:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return {"entries": entries[-50:], "total_logged": len(lines)}
