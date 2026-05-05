"""Schema tests for ``ReportRequest.SCENARIOS``.

The orchestrator-level scenario selection is now applied directly via
``create_scenario_object(scenario_names=req.SCENARIOS)`` — there is no
intermediate filter helper to test. What remains here is the request
schema contract: the picker UI sends a list of ids, and an unset field
preserves the legacy "process every subfolder" behaviour.
"""
from __future__ import annotations

from pipeline.services.report import ReportRequest


def test_report_request_accepts_scenarios_field() -> None:
    """The form payload carries the picker's selection as a list of IDs."""
    req = ReportRequest(
        PATH="C:/runs",
        CLIENT_NAME="C",
        PROJECT_NAME="P",
        PROJECT_LOCATION="L",
        EMAIL_PREFIX="ian",
        SCENARIOS=["FS1_FSA", "FS3_MOE"],
    )
    assert req.SCENARIOS == ["FS1_FSA", "FS3_MOE"]


def test_report_request_scenarios_defaults_to_none() -> None:
    """Backwards-compat: omitting SCENARIOS preserves the legacy
    "process every subfolder" behaviour."""
    req = ReportRequest(
        PATH="C:/runs",
        CLIENT_NAME="C",
        PROJECT_NAME="P",
        PROJECT_LOCATION="L",
        EMAIL_PREFIX="ian",
    )
    assert req.SCENARIOS is None
