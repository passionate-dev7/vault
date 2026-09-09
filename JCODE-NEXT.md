# WORK ORDER: Redslip, open the worst reject on load

You are in `projects/vault`. Wordmark is **Redslip**.

The ledger now defaults to FAIL (25 rejects). Sort-by-failures is already the active sort. A judge still has to click a row to see findings, the plot, and the slip. Accord opens on the work.

## Do this

1. Keep the ledger. Do not restyle.
2. After the catalog loads and FAIL rows are rendered, auto-expand the first visible FAIL row (the worst, given the existing failures sort). Call the existing expand path. Do not start triage. Do not call Gemini. If there are zero FAIL rows, expand nothing.
3. A check that would fail if a PASS row is expanded when FAIL rows exist, and would fail if nothing is expanded when FAIL rows exist. Use the real `/api/catalog` payload.
4. No Inter, no em dash, no emoji, no VAULT copy.

## Done when

A QC lead who opens Redslip is already looking at the worst failing title's findings, plot, and Copy slip control.
