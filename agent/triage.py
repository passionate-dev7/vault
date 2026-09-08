"""Gemini-powered triage agent that queries ClickHouse through MCP.

Architecture: deterministic measurements + model interpretation.
Gemini reads numbers that ffmpeg produced and produces a rescue plan.
It never invents a measurement — every claim it makes cites a row from the DB.

The MCP query path is load-bearing: delete mcp-clickhouse and the catalog
view dies (the agent cannot answer "which titles fail" or "cheapest to rescue").
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

log = logging.getLogger(__name__)

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# --- Gemini client --------------------------------------------------------

def _gemini():
    try:
        from google import genai
    except ImportError:
        return None

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true" and project:
        return genai.Client(
            vertexai=True,
            project=project,
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return None


# --- MCP-sourced catalog queries -----------------------------------------

async def _mcp_catalog_data() -> dict:
    """Fetch catalog data from ClickHouse via MCP. Returns raw results."""
    from agent.mcp_client import MCPClickHouseClient

    results = {}
    async with MCPClickHouseClient() as mcp:
        # Total row counts
        results["loudness_row_count"] = await mcp.query(
            "SELECT formatReadableQuantity(count()) FROM vault.loudness_samples"
        )
        results["findings_row_count"] = await mcp.query(
            "SELECT formatReadableQuantity(count()) FROM vault.findings"
        )
        results["title_count"] = await mcp.query(
            "SELECT count(DISTINCT title_id) FROM vault.findings"
        )

        # Catalog summary: failures per title
        results["catalog"] = await mcp.query(
            "SELECT title_id, title, failures, passes, auto_fixable, needs_human, verdict "
            "FROM vault.catalog_summary ORDER BY failures DESC LIMIT 30"
        )

        # Worst loudness per failing title
        results["loudness_extremes"] = await mcp.query(
            "SELECT le.title_id, le.integrated_lufs, le.worst_short_term_lufs, "
            "le.max_true_peak_dbfs, le.sample_count, le.worst_window_at_seconds "
            "FROM vault.loudness_extremes le "
            "JOIN vault.catalog_summary cs ON le.title_id = cs.title_id "
            "WHERE cs.verdict = 'FAIL' "
            "ORDER BY le.integrated_lufs ASC LIMIT 20"
        )

        # Titles where only auto-fixable issues remain
        results["auto_fixable_only"] = await mcp.query(
            "SELECT title_id, title, auto_fixable AS auto_fixable_count, failures "
            "FROM vault.catalog_summary "
            "WHERE needs_human = 0 AND failures > 0 "
            "ORDER BY auto_fixable DESC LIMIT 10"
        )

        # Titles needing human (structural defects)
        results["needs_human"] = await mcp.query(
            "SELECT title_id, title, needs_human, failures "
            "FROM vault.catalog_summary "
            "WHERE needs_human > 0 ORDER BY needs_human DESC LIMIT 10"
        )

        # Sample of individual findings for Gemini context
        results["sample_findings"] = await mcp.query(
            "SELECT title_id, title, check_name, measured, target, unit, passed, rescue_cost "
            "FROM vault.findings "
            "WHERE passed = 0 "
            "ORDER BY title_id, check_name LIMIT 60"
        )

    return results


TRIAGE_PROMPT = """You are a delivery operations manager at a film archive.

Below is catalog-scale QC data measured by ffmpeg on {title_count} public-domain titles,
stored in ClickHouse (total loudness samples: {loudness_rows}, findings rows: {findings_rows}).
Every number was produced by a machine measurement tool, never estimated.
Your job: produce a prioritised rescue plan.

Rules you MUST follow:
- Never invent a measurement. Every claim must cite a number from the data below.
- If a title has only auto-fixable failures (loudness, subtitle timing), mark it "BATCH".
- If a title has structural defects (black frames, freeze), mark it "MANUAL REVIEW".
- If a title passes all checks, mark it "DELIVERY READY".
- Rank failures by severity: LUFS delta > 3 LU is the worst loudness class.
- State rescue cost in words, not dollars.

CATALOG SUMMARY (latest QC run per title):
{catalog}

LOUDNESS EXTREMES (failing titles, quietest first):
{loudness_extremes}

AUTO-FIXABLE ONLY (no human needed):
{auto_fixable}

NEEDS HUMAN (structural defects present):
{needs_human}

SAMPLE FINDINGS (raw measurements):
{sample_findings}

Return strict JSON:
{{
  "summary": "two sentences for the archive manager",
  "total_titles": <int>,
  "failing": <int>,
  "passing": <int>,
  "auto_fixable": <int>,
  "needs_human": <int>,
  "rescue_plan": [
    {{
      "priority": <1-based int, 1=worst>,
      "title_id": "...",
      "title": "...",
      "verdict": "FAIL"|"PASS",
      "action": "BATCH"|"MANUAL REVIEW"|"DELIVERY READY",
      "measured_lufs": <float or null>,
      "lufs_delta": <float or null, absolute deviation from -23 LUFS target>,
      "failures": <int>,
      "rescue_cost": "...",
      "rationale": "one sentence citing a measured number"
    }}
  ],
  "operator_note": "three sentences: what to do first, what to defer, honest limit of this scan"
}}
"""


async def generate_triage_report() -> dict:
    """Query ClickHouse via MCP, then have Gemini produce the rescue plan."""
    catalog_data = await _mcp_catalog_data()

    # Count titles
    try:
        n_titles = int(catalog_data.get("title_count", "0").strip().split()[0])
    except Exception:
        n_titles = "?"

    prompt = TRIAGE_PROMPT.format(
        title_count=n_titles,
        loudness_rows=catalog_data.get("loudness_row_count", "?"),
        findings_rows=catalog_data.get("findings_row_count", "?"),
        catalog=catalog_data.get("catalog", "(no data)")[:3000],
        loudness_extremes=catalog_data.get("loudness_extremes", "(no data)")[:2000],
        auto_fixable=catalog_data.get("auto_fixable_only", "(no data)")[:1000],
        needs_human=catalog_data.get("needs_human", "(no data)")[:1000],
        sample_findings=catalog_data.get("sample_findings", "(no data)")[:3000],
    )

    g = _gemini()
    if g is None:
        log.warning("Gemini not configured; returning deterministic triage")
        return _deterministic_triage(catalog_data)

    try:
        resp = g.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        result = json.loads(resp.text)
        result["model"] = MODEL
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["mcp_data"] = {k: v[:200] for k, v in catalog_data.items()}
        return result
    except Exception as exc:
        log.error("Gemini failed: %s", exc)
        return _deterministic_triage(catalog_data)


def _deterministic_triage(catalog_data: dict) -> dict:
    """Fallback triage when Gemini is unavailable."""
    return {
        "summary": "Deterministic fallback (no Gemini credentials). "
                   "Check logs/mcp_tool_calls.jsonl for MCP evidence.",
        "mcp_data": {k: v[:200] for k, v in catalog_data.items()},
        "model": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_triage() -> dict:
    """Synchronous entry point for the web app."""
    return asyncio.run(generate_triage_report())
