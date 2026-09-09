"""The ledger opens on the rejects.

Real material only: rows come from the live /api/catalog payload, and the
filtering maths is the shipped verdictRows lifted out of web/index.html and
run under node.

Goes red both ways:
  - a default view that lets a PASS row through while FAIL rows exist
  - a FAIL chip that hands back a PASS title
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
    assert "FAIL" in verdicts, "no failing title, so the default view is untested"
    assert "PASS" in verdicts, "no passing title, so the leak is undetectable"
    return rows


def _verdict_rows(rows, verdict):
    """Run the page's own filter."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = INDEX.read_text(encoding="utf-8")
    fn = re.search(r"^function verdictRows.*?^}", src, re.S | re.M)
    assert fn, "verdictRows not found in index.html"

    script = f"""
{fn.group(0)}
console.log(JSON.stringify(verdictRows({json.dumps(rows)}, {json.dumps(verdict)})));
"""
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


def test_the_default_chip_is_fail():
    src = INDEX.read_text(encoding="utf-8")
    assert re.search(r'verdictFilter\s*=\s*"FAIL"', src), "ledger does not open on FAIL"
    assert re.search(
        r'id="chip-FAIL"[^>]*class="[^"]*active|class="chip active"[^>]*id="chip-FAIL"', src
    ), "the FAIL chip is not the one marked active on load"


def test_the_opening_view_shows_no_passing_title():
    rows = _catalog()
    shown = _verdict_rows(rows, "FAIL")
    assert shown, "the opening view is empty while the catalog has failures"
    leaked = [r["title_id"] for r in shown if r["verdict"] == "PASS"]
    assert not leaked, f"the FAIL chip showed passing titles: {leaked}"


def test_each_chip_holds_its_own_titles_and_all_holds_every_one():
    rows = _catalog()
    fail = _verdict_rows(rows, "FAIL")
    pas = _verdict_rows(rows, "PASS")
    every = _verdict_rows(rows, "ALL")

    assert {r["verdict"] for r in fail} == {"FAIL"}
    assert {r["verdict"] for r in pas} == {"PASS"}
    assert len(every) == len(rows)
    assert len(fail) + len(pas) == len(rows), "a title fell between the two chips"
