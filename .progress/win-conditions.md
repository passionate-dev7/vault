# Win conditions: Redslip, ClickHouse track

Internal. Gitignored, and deliberately not in `docs/`: the first line below names
competing entries and the bar we are aiming at, which is our working note and not
something a judge should read off our own repo.

Scoreboard: Two ClickHouse-track entries Grok's live retrieval names as already shipping the winning shape. `gaffer`, a code-ordered ADK crew whose ClickHouse read feeds one fusion step, owns its dispatch policy in code the model cannot reorder. `studio-crisis-commander`, detection as pure SQL with zero LLM, investigation through mcp-clickhouse, decision behind approval gates, owns the property that every figure comes from a query result. Also on the track: Cliffhanger, Cutting Room Copilot, cut-point, signaldrop, Accord. Usage numbers are not public for any of them; the observable asset each owns is the access pattern, not a user count.

Bar to beat: 3 winning slots. A compliant entry that holds the official `mcp-clickhouse` server through Google ADK and runs agent-authored SQL against ClickHouse Cloud from a live URL. Measured today, Redslip runs 4 agents, 3 agent-authored statements per run, 20 titles, 24,017 sample rows, 29 defect events, 82 seconds end to end, and prices every agent-authored statement out of `system.query_log`, which is ClickHouse's own per-statement accounting rather than anything counted in Python.

Asset we will own: The access pattern, obtained by measuring public archive.org masters with ffmpeg and laying the results out for the two questions that matter. `vault.title_loudness` is an AggregatingMergeTree kept current by a materialized view, so ranking the catalog reads one row per title and zero rows of the 100ms stream, provable with `EXPLAIN indexes = 1` and priced at 320 rows read against a 24,017-row stream. The stream is read only for an `ASOF JOIN` that stamps each defect with the loudness at the instant it began, which is what separates a reel change from dropout. Decisions land in `vault.slips`. Fat append-only series, small interactive rollup, point-in-time join, ledger of what was decided.

Off-platform buyer: The catalog or mastering QC lead at an indie distributor or film archive, the person who decides which titles get mix-stage time this week. Today they pay per seat for Telestream Vantage or Venera Pulsar, or they listen by ear.

Single entry: Redslip

Verb the brief names: "orchestrate", and "show off a deterministic, multi-step agent". The rules page adds "solve critical bottlenecks across the entertainment and media value chain".

Our product performs that verb: Yes. `agent/crew.py` builds a `SequentialAgent` named `redslip_triage`: `fleet_scout` ranks off the rollup and chooses the queue depth, a `ParallelAgent` runs `loudness_analyst` over `vault.loudness_samples` and `structural_analyst` over `vault.latest_events` ASOF-joined to loudness, then `work_allocator` holds no database tools and turns their evidence into an ordered queue with a bay per title. `run_crew` in the same file drives it and streams every composed statement. The queue is written back to ClickHouse by `_persist` in `web/app.py`.

Metric plan: 20 titles measured, 17 failing, worst 14.2 LU from the EBU R128 target of -23.0 LUFS. Checked at `/api/stats` and `/api/catalog` against `vault.fleet`, and re-checked independently with `ffmpeg -af ebur128` against the public source URL stored in `vault.sources` and printed next to every measurement. Cost is checked at `/api/query-cost` against the server's own `X-ClickHouse-Summary` header, and per agent-composed statement against `system.query_log`.

Live by: 2026-09-08, live now at https://vault-387894104564.us-central1.run.app on Cloud Run against ClickHouse Cloud, ahead of the 2026-09-09 deadline.

Deviation from research: Two, both deliberate. Grok argued for a LoopAgent planner/auditor pair; rejected, because paying a second model to check the first cannot be tested, so verification is a Python equality check against the returned cells in `verify_against_cells`. Grok also argued for inflating the demonstrated row count with a generator; rejected, because Potential Impact is scored on what is demonstrated and a row generator in the repo scores worse than an honest 24,017.

---

## Judging criteria this is scored against

Four, equally weighted. Technological Implementation (Google Cloud AND the partner service). Design (a complete product experience, not a proof of concept). Potential Impact (scored on what is demonstrated). Quality of the Idea (non-obvious use of Google Cloud plus partner).

The ClickHouse track is scored by ClickHouse's Director of Engineering AI/ML and a full-stack AI/ML engineer, the people who wrote `mcp-clickhouse`, plus roughly thirteen Google engineers and PMs. A compliant six beats a non-compliant eight, so compliance is the floor and the access pattern is the differentiator.

## Track discipline

One entry, one track. `grafana_board` is a fifth agent holding the official `mcp-grafana` server and it is a genuine bonus, but Redslip is submitted to ClickHouse. That agent therefore degrades rather than raises: with no Grafana token the four-agent ClickHouse crew runs to completion and the board step reports itself skipped, with the reason. With a token present it is in the graph and is not optional, so it is load-bearing where it is claimed and never a toggle that breaks the product for a ClickHouse judge.

## Honest limits carried into every surface

Each title is measured over its first 120 seconds, stated wherever a number appears. None of the 20 titles ships an SRT, so the Netflix TTSS checks are exercised by tests rather than by this catalog. The 28,423-title figure is a projection and is labelled as one. Nobody has run this in production.

## Open, named rather than quietly dropped

The hostile ClickHouse-judge critique of 2026-09-09 landed three findings this
workstream did not have time to close, and none of them are closed by a doc saying so.
The `ASOF` join annotates a defect but cannot move `vault.fleet.lane`, which is computed
from `findings.auto_fixable` alone. `FLAT`/`WIDE` is a threshold in a prompt rather than
a state on the rollup. Subtitle cues past the 120s window are scored against audio that
was never measured there. All three are schema changes against a live deployed service
inside the last hour before a deadline, which is the one trade this project does not make.
