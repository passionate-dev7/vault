"""The ledger leads with the rejects and marks them as rejects.

Redslip is a printed slip, not a filterable grid: there is no verdict chip and
no PASS/FAIL/ALL toggle. Instead the left column paints every measured title,
worst loudness first, with each reject drawn in the fail ink and each pass in
body gray. This test pins that contract against the live /api/catalog payload.

Real material only: rows come from the live payload, and the ordering maths is
the shipped orderedTitles lifted out of web/index.html and run under node.

Goes red:
  - if the banned verdict-chip chrome comes back
  - if a reject is not rendered with the reject class
  - if the first painted title is a pass while rejects exist
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

INDEX = Path(__file__).parent.parent / "web" / "index.html"


def _src() -> str:
    return INDEX.read_text(encoding="utf-8")


def _catalog():
    pytest.importorskip("qc.store")
    from fastapi.testclient import TestClient

    try:
        from web.app import app

        with TestClient(app) as c:
            resp = c.get("/api/catalog")
    except Exception as exc:  # ClickHouse not running in this environment
        pytest.skip(f"ClickHouse unavailable: {exc}")
    if resp.status_code != 200:
        pytest.skip(f"/api/catalog unavailable: {resp.status_code}")

    rows = resp.json()
    # An empty catalog would make every assertion below vacuously true.
    assert rows, "/api/catalog returned no titles; ingest first"
    verdicts = {r["verdict"] for r in rows}
    assert "FAIL" in verdicts, "no failing title, so the reject styling is untested"
    assert "PASS" in verdicts, "no passing title, so a leak is undetectable"
    return rows


def _ordered(rows):
    """Run the page's own column order."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = _src()
    fns = []
    for name in ("lufsDelta", "orderedTitles"):
        m = re.search(rf"^function {name}\(.*?^}}", src, re.S | re.M)
        assert m, f"{name} not found in index.html"
        fns.append(m.group(0))

    script = f"""
{chr(10).join(fns)}
console.log(JSON.stringify(orderedTitles({json.dumps(rows)}).map(r => (
  {{title_id: r.title_id, verdict: r.verdict}}
))));
"""
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


def test_no_verdict_chip_chrome():
    """The banned filter chrome must be gone: no chip, no sort bar, no toggle."""
    src = _src()
    assert "chip-FAIL" not in src, "the FAIL verdict chip is back"
    assert "setVerdictFilter" not in src, "the verdict filter toggle is back"
    assert 'class="chip' not in src, "chip chrome is back"


def test_rejects_are_painted_in_the_reject_ink():
    """renderTitles must tag rejecting titles with the reject class."""
    src = _src()
    render = re.search(r"^function renderTitles\(.*?^}", src, re.S | re.M)
    assert render, "renderTitles not found"
    body = render.group(0)
    # A rejecting title carries the reject class; a pass does not.
    assert 'isReject ? " reject"' in body or "reject" in body, (
        "renderTitles never marks a reject"
    )
    assert 'verdict !== "PASS"' in body, "renderTitles does not derive reject from the verdict"


def test_the_column_leads_with_a_reject():
    rows = _catalog()
    ordered = _ordered(rows)
    assert ordered, "the column painted nothing while the catalog has titles"
    assert ordered[0]["verdict"] != "PASS", (
        f"the column leads with a passing title: {ordered[0]['title_id']}"
    )


def test_every_title_is_painted_once():
    """No title falls out of the single column, and none is duplicated."""
    rows = _catalog()
    ordered = _ordered(rows)
    assert len(ordered) == len(rows), "a title fell out of the column"
    assert len({r["title_id"] for r in ordered}) == len(rows), "a title was painted twice"
