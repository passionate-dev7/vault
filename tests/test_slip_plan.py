"""The red slip must carry the rescue plan when triage has run, and name the
next action when it has not.

Extracts the slip functions out of web/index.html and exercises them under node,
so the assertions run against the shipped source rather than a copy.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).parent.parent / "web" / "index.html"
TID = "night_of_the_living_dead"

HARNESS = """
globalThis.allRows = [{title_id: TID, title: "Night of the Living Dead",
                       failures: 2, auto_fixable: 1, needs_human: 1}];
detailCache[TID] = {findings: [
  {check_name:"integrated_loudness", measured:-31.4, target:-23, unit:"LUFS",
   passed:0, auto_fixable:1, rescue_cost:"batch loudnorm", spec:"EBU R128"},
  {check_name:"black_frames", measured:12, target:0, unit:"frames",
   passed:0, auto_fixable:0, rescue_cost:"manual review"},
]};

const out = {};
lastTriage = null;
out.untriaged = buildSlip(TID);

lastTriage = {
  model: "gemini-2.5-flash",
  operator_note: "Batch the loudness titles tonight. Defer the structural ones.",
  rescue_plan: [
    {priority:1, title_id:TID, title:"Night of the Living Dead", action:"MANUAL REVIEW",
     measured_lufs:-31.4, lufs_delta:8.4, failures:2, rescue_cost:"one operator pass",
     rationale:"Integrated loudness measured -31.4 LUFS, 8.4 LU under target."},
    {priority:2, title_id:"other_film", title:"Other Film", action:"BATCH",
     failures:1, rescue_cost:"batch"},
  ]
};
out.triaged = buildSlip(TID);

lastTriage = {model:"m", rescue_plan:[{priority:1, title_id:"unrelated",
                                       title:"Unrelated", action:"BATCH"}]};
out.absent = buildSlip(TID);

console.log(JSON.stringify(out));
"""

NEXT_ACTION = "PLAN: not triaged. Click Re-triage selected title."


def _slips():
    """Run the page's own slip builder under node and return the three slips."""
    if not shutil.which("node"):
        pytest.skip("node not available")

    src = INDEX.read_text(encoding="utf-8")

    rescue = re.search(r"^function rescueText.*?^}", src, re.S | re.M)
    slip = re.search(r"^// .. Red slip.*?(?=^function copySlip)", src, re.S | re.M)
    assert rescue and slip, "slip functions not found in index.html"

    script = f'const TID = {json.dumps(TID)};\n{rescue.group(0)}\n{slip.group(0)}\n{HARNESS}'
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_untriaged_slip_names_the_next_action():
    slips = _slips()
    assert NEXT_ACTION in slips["untriaged"]
    assert "Rationale:" not in slips["untriaged"]


def test_triaged_slip_carries_the_plan():
    slip = _slips()["triaged"]
    assert "\nPLAN\n" in slip
    assert "Action:    MANUAL REVIEW" in slip
    assert "8.4 LU under target" in slip
    assert "Defer the structural ones" in slip
    assert NEXT_ACTION not in slip


def test_plan_does_not_leak_another_title():
    slips = _slips()
    assert "other_film" not in slips["triaged"]
    assert "Other Film" not in slips["triaged"]
    # Triage ran but skipped this title: still owes the reviewer a next action.
    assert NEXT_ACTION in slips["absent"]


def test_slip_keeps_the_failed_checks_and_cost():
    slip = _slips()["triaged"]
    assert "FAILED CHECKS" in slip
    assert "integrated_loudness" in slip
    assert "COST TO RESCUE" in slip
