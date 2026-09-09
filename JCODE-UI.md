# WORK ORDER: rebuild Redslip so the first screen is a printed slip

You are Claude Opus. Effort high. Visual judgment is the job. Do not add a FAIL chip or an auto-expand. Rebuild the first viewport.

Wordmark **Redslip**. You are in `projects/vault`. Rewrite `web/index.html`. Keep `/api/catalog`, `/api/title/{id}`, `/api/triage`, `/api/stats`. Do not introduce Next.js or Inter.

## Why the current page is slop

Playfair Display is the default "editorial AI" serif. The page is a SaaS table: three stat numbers, sort chips, expandable rows. A QC lead who rejects a delivery writes a slip. They do not filter a grid.

## Design Read (already locked)

`.uicraft-read.json` exists. Tokens from `DESIGN.md` (Wired) with one substitution:
- Display: **Newsreader** (Google Fonts), not Playfair. Playfair is the tell. Wired wants a tall narrow news serif. Newsreader at 64-88px, weight 400, tracking slightly negative.
- Reading: Source Serif 4 or Newsreader at 19px.
- Utility: Apercu substitute is Helvetica Neue / system sans. Mono: JetBrains Mono for LUFS only.
- Canvas: `#ffffff`. Ink: `#000`. Link blue `#057dbc`. Fail ink `#c81e1e`.
- Radius: 0. Hairline rules, not cards.
- Showpiece: none.

Obey uicraft contract. `uicraft gate --cwd web` then `uicraft look --url http://127.0.0.1:8081`.

## First viewport (this is the product)

A printed slip, full page, like a letter on white stock.

LEFT (~38%): newspaper column of titles. Each line is title, integrated LUFS vs -23, fail count. Fail titles in fail ink. Pass titles in body gray. No table header row of "Title / LUFS / Failures / Rescue / Verdict". No sort chip bar. Default order: worst LUFS delta first. Clicking a line sets the slip.

RIGHT (~62%): the slip for the selected title, already filled on load with the worst FAIL (from `/api/catalog` + `/api/title/{id}`). Typeset as a letter:

```
REDSLIP
delivery rejected
<title>
Integrated  <n> LUFS    spec  -23 ±1
<each failed check, measured vs spec>
LISTEN  <mm:ss>
PLAN    <triage text or: not triaged>
```

**Copy slip** is a text control under the letter, same as now (execCommand first). PLAN and LISTEN stay when that data exists. The loudness plot is a hairline under the slip, with the listen marker, or it is omitted if it fights the letter. Prefer the letter.

Masthead is the word **Redslip** in Newsreader, one line, with a 2px black rule under it. Standfirst is one sentence, Source Serif, max 62ch: what the page is. Not a product tagline.

## Hard bans

Playfair. Inter. Stat-number band of three KPIs. Sort chips. Expandable table rows. Pills. Cards. Shadows. Dark mode. Emoji. Em dash. En dash. Green pass badges as the first thing you see.

## Done when

1. `uicraft gate --cwd web` exits 0 (the current en-dash on A-Z sort must be gone because that chrome is gone).
2. `uicraft look --url http://127.0.0.1:8081` at 1440. Name remaining tells. Fix them.
3. A judge at 8 seconds is reading a rejection letter, not a spreadsheet.
4. Commit.

Keep copySlip, planFor, listenLines behaviour. Restyle is allowed. The letter is the product.
