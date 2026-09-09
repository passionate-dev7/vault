"""Redslip opens already reading the slip for the worst reject.

Real material only: rows come from the live /api/catalog payload, and the
choice of which title to select on load is the shipped openingFailId lifted
out of web/index.html and run under node with the page's own opening state.

The page is a printed slip, not a table: the left column paints titles worst
loudness delta first, and the right slip is filled on load with the worst
reject. There is no verdict chip, no sort bar, no expandable row.

Goes red:
  - if the title selected on load is a PASS while rejects exist
  - if nothing is selected while rejects exist
  - if it is not the worst reject in the painted order
  - if load never calls the selection path
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
    assert "FAIL" in verdicts, "no failing title, so there is nothing to open on"
    assert "PASS" in verdicts, "no passing title, so a wrong pick is undetectable"
    return rows


def _run(rows):
    """Run the page's own pick, plus the order the column paints."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = _src()
    fns = []
    for name in ("lufsDelta", "orderedTitles", "openingFailId"):
        m = re.search(rf"^function {name}\(.*?^}}", src, re.S | re.M)
        assert m, f"{name} not found in index.html"
        fns.append(m.group(0))

    script = f"""
{chr(10).join(fns)}
console.log(JSON.stringify({{
  picked:  openingFailId({json.dumps(rows)}),
  ordered: orderedTitles({json.dumps(rows)}).map(r => r.title_id),
}}));
"""
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


def test_load_runs_the_selection_path():
    src = _src()
    load = re.search(r"^async function loadCatalog\(.*?^}", src, re.S | re.M)
    assert load, "loadCatalog not found"
    assert "openWorstFailure()" in load.group(0), "the catalog load never opens a slip"

    opener = re.search(r"^function openWorstFailure\(.*?^}", src, re.S | re.M)
    assert opener, "openWorstFailure not found"
    body = opener.group(0)
    assert "selectTitle(" in body, "the opener does not use the existing selection path"
    # Opening a slip must not start triage or reach for the model.
    for forbidden in ("gemini", "triage", "runTriage"):
        assert forbidden.lower() not in body.lower(), f"the opener touches {forbidden}"


def test_the_title_selected_on_load_is_the_worst_reject():
    rows = _catalog()
    out = _run(rows)

    picked = out["picked"]
    assert picked is not None, "rejects exist but the ledger selected nothing"

    by_id = {r["title_id"]: r for r in rows}
    assert by_id[picked]["verdict"] != "PASS", f"the ledger opened a passing title: {picked}"

    # It must be the first reject in the order actually painted.
    first_reject = next(t for t in out["ordered"] if by_id[t]["verdict"] != "PASS")
    assert picked == first_reject, f"opened {picked}, but {first_reject} sits above it"


def _lufs_delta(row):
    v = row.get("integrated_lufs")
    if v is None:
        return None
    return abs(float(v) - (-23))


def test_the_worst_reject_is_the_furthest_from_target():
    """The column heads on the largest loudness delta, and that is what opens."""
    rows = _catalog()
    out = _run(rows)
    picked = out["picked"]
    by_id = {r["title_id"]: r for r in rows}

    measured_rejects = [
        _lufs_delta(by_id[t])
        for t in out["ordered"]
        if by_id[t]["verdict"] != "PASS" and _lufs_delta(by_id[t]) is not None
    ]
    # Only assert the loudness ordering when the worst reject is a measured one.
    if _lufs_delta(by_id[picked]) is not None:
        assert measured_rejects, "measured reject picked but none found in order"
        assert abs(_lufs_delta(by_id[picked]) - max(measured_rejects)) < 1e-6, (
            "a reject further from -23 LUFS was left below the opened one"
        )


def test_the_column_puts_unmeasured_titles_last():
    """A title with no loudness cannot masquerade as on-spec at the top."""
    rows = _catalog()
    out = _run(rows)
    by_id = {r["title_id"]: r for r in rows}
    deltas = [_lufs_delta(by_id[t]) for t in out["ordered"]]

    # Once a None appears, no measured title may follow it.
    seen_none = False
    for d in deltas:
        if d is None:
            seen_none = True
        else:
            assert not seen_none, "a measured title sits below an unmeasured one"
