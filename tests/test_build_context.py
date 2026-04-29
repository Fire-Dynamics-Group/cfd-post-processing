"""Characterization tests for ``build_context``.

The plan (PR2_PLAN.md Q10) pins the contract via golden JSON: each fixture
is a cached ``scenarios_object`` (the dict ``create_scenario_object``
returns) plus an ``expected_ctx.json`` snapshot of what ``build_context``
produces for that input. If the orchestrator's ctx shape drifts, this test
goes red — that's the "characterization" part.

Bootstrapping a new fixture:
    Set CFD_UPDATE_SNAPSHOTS=1 and run the test once. The expected ctx
    file is written. Re-run without the env var to verify the snapshot.

Reviewing a snapshot diff: open ``expected_ctx.json`` and read it like a
spec — every key in there is a docxtpl tag the template depends on.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from pipeline.services.report import ReportRequest, build_context


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_scenarios(path: Path) -> dict[str, Any]:
    """``json.load`` accepts ``NaN`` tokens by default; the resulting floats
    round-trip through ``scen_results_values`` correctly because that
    function already does its own ``math.isnan`` checks."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalise_for_compare(value: Any) -> Any:
    """Replace ``nan`` with the sentinel ``"__NaN__"`` so equality holds.

    ``nan != nan``, which would otherwise make every snapshot trivially
    diff. This matches what we write into the golden file.
    """
    if isinstance(value, float) and math.isnan(value):
        return "__NaN__"
    if isinstance(value, dict):
        return {k: _normalise_for_compare(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise_for_compare(v) for v in value]
    return value


def _stable_request(project_name: str, guidance: str = "BS9991") -> ReportRequest:
    """Build a request with date-independent stable inputs.

    The orchestrator stamps ``TODAYS_DATE`` into ctx; the snapshot test
    overrides this key after build to keep the golden stable across days.
    """
    return ReportRequest(
        PATH="<<fixture>>",
        CLIENT_NAME="Test Client",
        PROJECT_NAME=project_name,
        PROJECT_LOCATION="Test Location",
        EMAIL_PREFIX="ian",
        HAS_EXTENDED_TRAVEL=True,
        MAX_TD=15,
        GUIDANCE=guidance,
    )


@pytest.fixture()
def update_snapshots() -> bool:
    return os.environ.get("CFD_UPDATE_SNAPSHOTS") == "1"


@pytest.mark.parametrize(
    "fixture_dir,project_name,guidance",
    [
        ("finchley_fs1", "Finchley_FS1", "BS9991"),
        ("mixed_moe_fsa", "MixedJob", "ADB"),
    ],
)
def test_build_context_matches_golden(
    fixture_dir: str,
    project_name: str,
    guidance: str,
    update_snapshots: bool,
) -> None:
    fixture_path = FIXTURES_DIR / fixture_dir
    scenarios_object = _load_scenarios(fixture_path / "scenarios_object.json")
    scenario_names = list(scenarios_object.keys())
    FSA_scenarios = [s for s in scenario_names if "FSA" in s]
    MoE_scenarios = [s for s in scenario_names if "FSA" not in s]

    req = _stable_request(project_name, guidance=guidance)
    ctx, ref_order = build_context(
        req=req,
        scenarios_object=scenarios_object,
        scenario_names=scenario_names,
        FSA_scenarios=FSA_scenarios,
        MoE_scenarios=MoE_scenarios,
        fds_version="6.7.7",  # frozen so the golden is date-independent.
    )

    # Stamp out date-dependent fields so the golden doesn't churn.
    ctx["TODAYS_DATE"] = "<<frozen>>"
    snapshot = {"ctx": _normalise_for_compare(ctx), "ref_order": ref_order}

    expected_path = fixture_path / "expected_ctx.json"
    if update_snapshots or not expected_path.exists():
        expected_path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )
        if not os.environ.get("CFD_UPDATE_SNAPSHOTS"):
            pytest.fail(
                f"Bootstrapped expected_ctx.json at {expected_path}. "
                "Re-run the test (without CFD_UPDATE_SNAPSHOTS=1) to verify.",
            )

    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert snapshot == expected
