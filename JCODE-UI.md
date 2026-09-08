# WORK ORDER: rebuild VAULT as a delivery-rejection ledger, not a dashboard

Rewrite `web/index.html` only. Do not change Python APIs in `web/app.py` unless a one-line bug blocks the page. Keep every existing fetch URL.

## Why it loses

WIRED tokens were applied onto dashboard leftovers: `.stats-bar`, `.stat-card`, `.badge` pills, `.overlay` modal, uppercase kickers, "MCP section". It still reads as a hackathon console in a serif costume. The product is a **catalog contents page**: which titles in this archive would be rejected today, ranked, each row a measured number.

## Visual system

Keep `DESIGN.md` (WIRED). Playfair Display + Source Serif 4 + Inter for utility + JetBrains Mono for numbers. White canvas, black ink, one link blue `#057dbc`, fail red `#c81e1e`. No cards. No pills. No dark mode. Sections separated by rules, like a magazine contents list.

## First viewport

Masthead: the word VAULT in Playfair, then one sentence that names the job. Then **the index is immediately visible**, not below three stat cards.

The index is the product:
- Rank
- Title (serif, the film's name)
- Integrated LUFS vs -23 (mono, fail in red if out of ±1)
- Failures (count)
- Rescue (what the row already stores: auto-fixable vs human)
- Verdict

Clicking a row expands **in place** (not a modal overlay): the measured checks, the worst window if present, and the MCP/agent note. A modal is a dashboard tell. An accordion row is a ledger.

Above the table, three numbers in Playfair at ~48-56px, not in cards: titles scanned, titles failing, titles that would pass after auto-repair. Baseline them. No "stat-card" boxes.

A single control to re-triage the selected title (`POST /api/triage`) as a text-style button, not a giant yellow CTA.

## MCP

`/api/mcp-log` is a footnote under the table: "queries the agent ran", mono, collapsed by default. Do not lead with it.

## APIs

- GET `/api/stats`
- GET `/api/catalog`
- GET `/api/title/{title_id}`
- POST `/api/triage`
- GET `/api/mcp-log`

Preserve field names the current JS already uses. Read `web/index.html` script and `web/app.py` before deleting any column.

## Hard bans

No emoji, no pills, no overlay modal, no Inter display type, no dark canvas, no yellow, no gradient, no "Loading…" as the only empty state (name the catalog). No em dash.

## Done

First screen is a ranked list of real titles with LUFS. Print 10 lines describing it.
