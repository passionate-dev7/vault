"""The slip must point a mixer at the quietest sustained passage.

Real rows only: the window numbers come out of ClickHouse (vault.loudness_extremes)
for a title that has one, and out of a real catalog title that has none. The slip
builder itself is the shipped one, extracted from web/index.html and run under node.

Goes red both ways:
  - a title WITH a stored window that copies a slip carrying no mm:ss timestamp
  - a title WITHOUT a stored window that gets any timestamp at all
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
MMSS = re.compile(r"\b\d{2}:\d{2}\b")


def _catalog_split():
    """One real title with a stored loudness window, one real title without."""
    store = pytest.importorskip("qc.store")
    try:
        catalog = [c["title_id"] for c in store.catalog_summary()]
        measured = {e["title_id"] for e in store.loudness_extremes()}
    except Exception as exc:  # ClickHouse not running in this environment
        pytest.skip(f"ClickHouse unavailable: {exc}")

    with_window = [t for t in catalog if t in measured]
    without = [t for t in catalog if t not in measured]
    assert with_window, "no catalog title has a loudness window; ingest first"
    assert without, (
        "every catalog title has a window, so the no-window branch is untested"
    )
    win = store.worst_window(with_window[0])
    assert win and win["quietest_at_seconds"] is not None
    assert store.worst_window(without[0]) is None
    return with_window[0], win, without[0]


def _slip(title_id: str, worst_window) -> str:
    """Build the slip with the page's own code for one title."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = INDEX.read_text(encoding="utf-8")
    rescue = re.search(r"^function rescueText.*?^}", src, re.S | re.M)
    slip = re.search(r"^// .. Red slip.*?(?=^function copySlip)", src, re.S | re.M)
    assert rescue and slip, "slip functions not found in index.html"

    harness = f"""
const TID = {json.dumps(title_id)};
globalThis.allRows = [{{title_id: TID, title: TID, failures: 1,
                        auto_fixable: 0, needs_human: 1}}];
detailCache[TID] = {{
  findings: [{{check_name:"integrated_loudness", measured:-31.4, target:-23,
              unit:"LUFS", passed:0, auto_fixable:1, rescue_cost:"batch loudnorm"}}],
  worst_window: {json.dumps(worst_window)}
}};
lastTriage = null;
console.log(buildSlip(TID));
"""
    script = f"{rescue.group(0)}\n{slip.group(0)}\n{harness}"
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_a_measured_title_gets_a_timestamp_and_both_extremes():
    tid, win, _ = _catalog_split()
    slip = _slip(tid, win)

    assert "\nLISTEN\n" in slip, "slip for a measured title carries no LISTEN section"
    stamps = MMSS.findall(slip)
    assert stamps, "measured title copied a slip with no mm:ss timestamp"

    secs = int(win["quietest_at_seconds"])
    expected = f"{secs // 60:02d}:{secs % 60:02d}"
    assert expected in slip, f"expected {expected} from {win}, slip has {stamps}"

    assert f'{win["quietest_short_term_lufs"]:.1f} LUFS' in slip
    assert f'{win["loudest_short_term_lufs"]:.1f} LUFS' in slip
    assert "no loudness window stored" not in slip


def test_an_unmeasured_title_gets_no_invented_time():
    _, _, tid = _catalog_split()
    slip = _slip(tid, None)

    assert "LISTEN: no loudness window stored for this title." in slip
    assert not MMSS.findall(slip), f"fake timestamp on an unmeasured title: {slip}"


def test_the_api_hands_the_window_to_the_page():
    """The slip's input is real: /api/title carries the same numbers as the store."""
    store = pytest.importorskip("qc.store")
    tid, win, empty = _catalog_split()

    from fastapi.testclient import TestClient
    from web.app import app

    with TestClient(app) as c:
        assert c.get(f"/api/title/{tid}").json()["worst_window"] == win
        assert c.get(f"/api/title/{empty}").json()["worst_window"] is None
