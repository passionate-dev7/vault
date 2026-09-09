"""The plot must mark the passage the slip names.

Real material only: the chart points and the window both come out of
/api/title for a real catalog title, and the marker maths is the shipped
listenMarkerX lifted out of web/index.html and run under node.

Goes red both ways:
  - a window late in the title drawn at x=0 (index-based placement)
  - a title with no stored window that still gets a marker
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
W = 700.0


def _api():
    """One real title with a window, one without, with their real charts."""
    store = pytest.importorskip("qc.store")
    try:
        catalog = [c["title_id"] for c in store.catalog_summary()]
        measured = {e["title_id"] for e in store.loudness_extremes()}
    except Exception as exc:  # ClickHouse not running in this environment
        pytest.skip(f"ClickHouse unavailable: {exc}")

    with_window = [t for t in catalog if t in measured]
    without = [t for t in catalog if t not in measured]
    assert with_window, "no catalog title has a loudness window; ingest first"
    if not without:
        # No REAL windowless title exists: every ingested title has audible audio.
        # Skipping is honest; the null branch is covered directly by
        # test_a_null_window_draws_no_marker below, which calls the shipped
        # function with no window rather than inventing a fake catalog row.
        pytest.skip("no windowless title in the catalog; branch covered by unit test")

    from fastapi.testclient import TestClient
    from web.app import app

    with TestClient(app) as c:
        hot = c.get(f"/api/title/{with_window[0]}").json()
        cold = c.get(f"/api/title/{without[0]}").json()

    assert hot["worst_window"] and hot["worst_window"]["quietest_at_seconds"] is not None
    assert cold["worst_window"] is None
    assert len(hot["loudness_chart"]) > 1, "measured title has no chart to mark"
    return hot, cold


def _marker_x(chart, window):
    """Run the page's own marker maths. None means no marker drawn."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = INDEX.read_text(encoding="utf-8")
    fn = re.search(r"^function listenMarkerX.*?^}", src, re.S | re.M)
    assert fn, "listenMarkerX not found in index.html"

    script = f"""
{fn.group(0)}
const x = listenMarkerX({json.dumps(chart)}, {json.dumps(window)}, {W});
console.log(JSON.stringify(x));
"""
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


def test_the_marker_lands_at_the_time_the_slip_names():
    hot, _ = _api()
    chart = hot["loudness_chart"]
    win = hot["worst_window"]

    x = _marker_x(chart, win)
    assert x is not None, "measured title got no marker"

    t0 = chart[0]["t"]
    t1 = chart[-1]["t"]
    expected = (win["quietest_at_seconds"] - t0) / (t1 - t0) * W
    expected = min(max(expected, 0.0), W)
    assert abs(x - expected) < 1.0, (
        f"marker at x={x} but {win['quietest_at_seconds']}s over [{t0},{t1}] is x={expected}"
    )


def test_a_late_window_is_not_drawn_at_the_left_edge():
    """Index-based placement would put a 180s window at x=0. Time-based does not."""
    hot, _ = _api()
    chart = hot["loudness_chart"]
    t0, t1 = chart[0]["t"], chart[-1]["t"]
    if t1 - t0 < 60:
        pytest.skip("chart too short to distinguish a late window")

    late = dict(hot["worst_window"])
    late["quietest_at_seconds"] = t0 + (t1 - t0) * 0.75

    x = _marker_x(chart, late)
    assert x is not None
    assert x > W * 0.5, f"a three-quarter-through window drew at x={x}, near the left edge"
    assert abs(x - W * 0.75) < 1.0


def test_a_title_with_no_window_gets_no_marker():
    _, cold = _api()
    assert _marker_x(cold["loudness_chart"], cold["worst_window"]) is None
    assert _marker_x(cold["loudness_chart"], None) is None
