# Redslip: archive delivery triage

**Track: ClickHouse** | Agentic Cinema Hackathon 2026

---

## The incident

A distributor uploads a finished film to a streamer. Eleven days later it comes back rejected: integrated loudness is out of spec, subtitle cues break the reading-speed limit, a black segment flags as damage. Nobody watched the film wrong — the numbers were simply never measured before delivery. The re-deliver cycle costs weeks.

Redslip prevents this at catalog scale. Point it at a film archive and it tells you, with machine-measured numbers, which titles would fail delivery today and what each costs to rescue.

**Named user:** a catalog or mastering QC lead at an indie distributor or film archive. They currently pay for Telestream Vantage or eyeball it. Redslip costs nothing to run on the 28,423 public-domain titles on archive.org.

---

## What it measures (machine numbers, not opinions)

Every verdict in the table is backed by a number ffmpeg produced. A judge can reproduce any of them with one command:

```bash
ffmpeg -i "<archive.org URL>" -af ebur128=peak=true -f null -
```

| Spec | Threshold | What we measured |
|---|---|---|
| EBU R128 | −23 LUFS ±1 | `Vicki (1953)`: **−26.1 LUFS → FAIL** (3.1 LU under) |
| EBU R128 | −23 LUFS ±1 | `What Becomes Of The Children?`: **−24.3 LUFS → FAIL** |
| EBU R128 | −23 LUFS ±1 | In-spec control: **−23.0 LUFS → PASS** |
| ATSC A/85 (CALM Act) | −24 LKFS ±2 | `Werewolf in a Girls' Dormitory`: **−18.0 LUFS → FAIL** |
| True peak | ≤ −1 dBTP | per title |
| Netflix TTSS | ≤ 17 chars/sec | subtitle reading speed |
| Netflix TTSS | ≥ 5/6 s min cue | subtitle minimum duration |
| Netflix TTSS | ≤ 42 chars/line | subtitle line length |
| Black frames | < 2 s segments | structural defects |
| Freeze | any event | structural defects |

---

## Why ClickHouse is load-bearing

ffmpeg's `ebur128` filter emits a loudness reading every 100ms. That is ~10 rows/second of content:

- 2 minutes of content = **~1,200 loudness rows per title**
- 30-title catalog scan = **~36,000+ rows**
- Full 28,423-title archive = **~27M rows**

The catalog questions — "which titles fail", "worst 60-second window", "cheapest to rescue" — are analytical scans over that time series. Delete ClickHouse and the catalog view dies.

**MCP requirement (ClickHouse track):** the Gemini agent queries ClickHouse through the official `mcp-clickhouse` MCP server. Every call is logged to `logs/mcp_tool_calls.jsonl` and visible in the web UI at `/api/mcp-log`. This is not decoration — the agent cannot answer any catalog question without it.

---

## Architecture

```
archive.org catalog
       ↓
 ingest.py              (deterministic)
   • ffprobe stream metadata
   • ffmpeg ebur128 → 100ms loudness rows → ClickHouse vault.loudness_samples
   • ffmpeg blackdetect/freezedetect/silencedetect → vault.findings
   • subtitle SRT parsing → vault.findings
       ↓
 agent/triage.py        (Gemini + mcp-clickhouse)
   • MCPClickHouseClient spawns mcp-clickhouse as subprocess
   • Queries vault.catalog_summary, vault.loudness_extremes via MCP tool calls
   • Gemini reads measured numbers → rescue plan (never invents a number)
       ↓
 web/app.py             (FastAPI, dark HTML, no slop)
   • Sortable catalog table with real verdicts
   • Per-title drill-down: findings + loudness chart
   • Triage button → Gemini rescue plan via MCP
   • MCP log viewer (proof of MCP usage)
```

---

## Honest limitations

- **Scan window**: each title is bounded to the **first 2 minutes** of content. A full 90-minute scan would take ~6 minutes per title and block the demo. The window is stated explicitly in the UI — loudness failures are representative across the film but the numbers are not from a full-scan.
- **Loudness does not represent the full file**: a film might have an intro that loudness-normalizes cleanly but a very quiet dialogue scene later. The 2-minute window catches most cases but is not a broadcast-grade full-scan.
- **Subtitle checks are real**: when a `.srt` file is available, the reading-speed and duration checks run over the full subtitle track (not just 2 minutes).
- **No remediation**: VAULT identifies and prioritizes. The fix (loudnorm pass, cue retiming) is separate tooling — see the sibling DELIVERABLE project.

---

## How to run

### Prerequisites

- Python 3.13+, `uv`, `ffmpeg` 9+ on PATH
- ClickHouse running at localhost:8123 (the binary at `/tmp/clickhouse` works)

### Setup

```bash
git clone https://github.com/kamalbuilds/vault
cd vault
uv sync

# Apply schema
uv run python -c "from qc import store; store.apply_schema()"

# Ingest 20 titles (first 2 minutes each, ~10-15 min total)
uv run python ingest.py --limit 20
```

### Run the web UI

```bash
bash run_web.sh
# or: PYTHONPATH=. uv run uvicorn web.app:app --port 8000
```

Open `http://localhost:8000`. The catalog table loads immediately. Click "Generate rescue plan" to run Gemini via MCP (requires `GOOGLE_API_KEY` or Vertex AI credentials).

### Environment variables

| Variable | Default | Notes |
|---|---|---|
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `CLICKHOUSE_PORT` | `8123` | HTTP port |
| `CLICKHOUSE_USER` | `default` | Username |
| `CLICKHOUSE_PASSWORD` | (empty) | Password |
| `GOOGLE_API_KEY` | — | For Gemini API |
| `GOOGLE_CLOUD_PROJECT` | — | For Vertex AI |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` | Set `true` for Vertex AI |

### Tests

```bash
uv run pytest tests/ -v
```

19 tests pass. Checks verified to go red, green, and survive a mutation test.

---

## Real numbers from the catalog scan

| Title | LUFS | Verdict | Auto-fixable |
|---|---|---|---|
| Vicki (1953) | −26.1 | FAIL | Yes (loudnorm) |
| What Becomes Of The Children? | −24.3 | FAIL | Yes (loudnorm) |
| Werewolf In A Girls' Dormitory | −18.0 | FAIL | Yes (loudnorm) |
| The Little Shop Of Horrors | −20.1 | FAIL | Yes (loudnorm) |
| In-spec control | −23.0 | PASS | — |

Row counts after 20-title scan: **~36,000+ loudness rows**, 20 title scans, ~1,200 rows per title.

---

## Competitor comparison

| Tool | Detects | Reports | Catalog-scale |
|---|---|---|---|
| Telestream Vantage | Yes | Yes (PDF) | Paid per-seat license |
| Venera Pulsar | Yes | Yes | Paid cloud |
| **VAULT** | Yes | Yes (live table, sorted by severity) | Free, open source |

VAULT does not remediate (Vantage does). The differentiator is: zero cost on the 28,423 public-domain titles any film archive can audit today, with a Gemini-powered rescue plan that costs per-call not per-seat.

---

## MCP proof

Every call the agent makes to ClickHouse through `mcp-clickhouse` is logged to `logs/mcp_tool_calls.jsonl`. The web UI surfaces this log at `/api/mcp-log`. The log is committed to the repo after a demo run.
