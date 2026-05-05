"""Tests for the SCENARIOS filter applied after parsing in the report
orchestrator.

The Charts mode picker lets the user discover all scenarios under a path
then tick which ones to chart. Report mode mirrors that: the user picks a
subset, and the orchestrator must process only those — not the legacy
"everything under PATH" behaviour.

These tests pin a pure helper (``filter_scenarios``) so the orchestrator
wiring stays a one-liner and the filter logic is testable without needing
a real FDS run directory or rendering a docx.
"""
from __future__ import annotations

import pytest

from pipeline.services.report import filter_scenarios


def _scenarios_object(*names: str) -> dict[str, dict]:
    """Stand-in for the dict ``create_scenario_object`` returns. The filter
    only needs the keys; downstream consumers look up by scenario name."""
    return {n: {"placeholder": True} for n in names}


def test_filter_keeps_only_selected_ids_preserving_input_order() -> None:
    scenario_names = ["FS1_FSA", "FS2_FSA", "FS3_MOE"]
    fsa = ["FS1_FSA", "FS2_FSA"]
    moe = ["FS3_MOE"]
    scen_obj = _scenarios_object(*scenario_names)

    out_names, out_fsa, out_moe, out_obj = filter_scenarios(
        selected_ids=["FS1_FSA", "FS3_MOE"],
        scenario_names=scenario_names,
        FSA_scenarios=fsa,
        MoE_scenarios=moe,
        scenarios_object=scen_obj,
    )

    # Order follows the discovery order (scenario_names), not the order
    # in selected_ids — the report flow indexes scenarios sequentially
    # and a stable order avoids surprising "scenario 1 vs scenario 2"
    # numbering changes from a UI tick-order.
    assert out_names == ["FS1_FSA", "FS3_MOE"]
    assert out_fsa == ["FS1_FSA"]
    assert out_moe == ["FS3_MOE"]
    assert set(out_obj.keys()) == {"FS1_FSA", "FS3_MOE"}


def test_filter_returns_inputs_unchanged_when_selected_ids_is_none() -> None:
    """``None`` means "no filter applied" (legacy behaviour: process all)."""
    scenario_names = ["FS1_FSA", "FS2_MOE"]
    fsa = ["FS1_FSA"]
    moe = ["FS2_MOE"]
    scen_obj = _scenarios_object(*scenario_names)

    out_names, out_fsa, out_moe, out_obj = filter_scenarios(
        selected_ids=None,
        scenario_names=scenario_names,
        FSA_scenarios=fsa,
        MoE_scenarios=moe,
        scenarios_object=scen_obj,
    )

    assert out_names == scenario_names
    assert out_fsa == fsa
    assert out_moe == moe
    assert out_obj is scen_obj


def test_filter_raises_when_selected_id_does_not_match_any_scenario() -> None:
    """A typo / drift between discover and submit should fail loudly with a
    user-fixable error, not silently produce a report missing scenarios."""
    from pipeline.services.report import PipelineError

    with pytest.raises(PipelineError, match="not found"):
        filter_scenarios(
            selected_ids=["FS_does_not_exist"],
            scenario_names=["FS1_FSA"],
            FSA_scenarios=["FS1_FSA"],
            MoE_scenarios=[],
            scenarios_object=_scenarios_object("FS1_FSA"),
        )


def test_filter_raises_when_selected_ids_is_empty() -> None:
    """The frontend disables submit when zero are checked, so an empty list
    reaching here is a logic bug. Treat as PipelineError so the user gets a
    clear message rather than a confusing "no scenarios" downstream."""
    from pipeline.services.report import PipelineError

    with pytest.raises(PipelineError, match="empty"):
        filter_scenarios(
            selected_ids=[],
            scenario_names=["FS1_FSA"],
            FSA_scenarios=["FS1_FSA"],
            MoE_scenarios=[],
            scenarios_object=_scenarios_object("FS1_FSA"),
        )


def test_report_request_accepts_scenarios_field() -> None:
    """The form payload carries the picker's selection as a list of IDs."""
    from pipeline.services.report import ReportRequest

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
    from pipeline.services.report import ReportRequest

    req = ReportRequest(
        PATH="C:/runs",
        CLIENT_NAME="C",
        PROJECT_NAME="P",
        PROJECT_LOCATION="L",
        EMAIL_PREFIX="ian",
    )
    assert req.SCENARIOS is None
