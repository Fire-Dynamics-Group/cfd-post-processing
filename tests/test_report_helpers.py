"""Unit tests for the small helpers inside services.report.

These pin behavior the orchestrator depends on at multiple call-sites.
Each was identified by an e2e failure or by inspection of the legacy
``auto_report.run_report`` it replaces.
"""
from __future__ import annotations

import pytest

from pipeline.services.report import (
    _compute_fire_scen_text,
    _num_to_text,
    _ref_order_for,
)


class TestNumToText:
    def test_zero_returns_int_zero(self) -> None:
        # Legacy ``num_to_text`` returned the number unchanged when no word
        # mapping existed. A 0-MoE Finchley-style job exercises this path
        # via ``NUM_MOE_SCENARIOS_TEXT``.
        assert _num_to_text(0) == 0

    @pytest.mark.parametrize("num,expected", [
        (1, "one"), (2, "two"), (3, "three"), (4, "four"),
        (5, "five"), (6, "six"), (7, "seven"), (8, "eight"), (9, "nine"),
    ])
    def test_one_to_nine_returns_word(self, num: int, expected: str) -> None:
        assert _num_to_text(num) == expected

    def test_capitalised_word(self) -> None:
        assert _num_to_text(2, capitalise=True) == "Two"

    def test_ten_or_more_returns_int(self) -> None:
        assert _num_to_text(10) == 10
        assert _num_to_text(42) == 42


class TestComputeFireScenText:
    def test_single_fsa_no_moe(self) -> None:
        text = _compute_fire_scen_text(
            scenario_names=["FS1_FSA"],
            MoE_scenarios=[],
            FSA_scenarios=["FS1_FSA"],
        )
        assert text.startswith("One fire scenario has been considered")
        assert "Fire Service Access phase only" in text
        assert "credible worst case apartment location." in text

    def test_two_fsa_no_moe(self) -> None:
        # Finchley shape.
        text = _compute_fire_scen_text(
            scenario_names=["FS1_FSA", "FS2_FSA"],
            MoE_scenarios=[],
            FSA_scenarios=["FS1_FSA", "FS2_FSA"],
        )
        assert text.startswith("Two fire scenarios have been considered")
        assert "Fire Service Access phase only" in text
        assert "credible worst case apartment locations." in text

    def test_mixed_moe_and_fsa(self) -> None:
        text = _compute_fire_scen_text(
            scenario_names=["FS1_MOE", "FS2_FSA", "FS3_FSA"],
            MoE_scenarios=["FS1_MOE"],
            FSA_scenarios=["FS2_FSA", "FS3_FSA"],
        )
        assert "one Means of Escape scenario" in text
        assert "two Fire Service Access scenarios" in text


class TestRefOrderFor:
    def test_bs9991_appears_before_bs7974_when_bs9991(self) -> None:
        order = _ref_order_for("BS9991")
        assert order.index("BS9991") < order.index("BS7974")
        assert "ADB" not in order

    def test_adb_used_in_main_slot_and_bs9991_appended_when_adb(self) -> None:
        order = _ref_order_for("ADB")
        assert order.index("ADB") < order.index("BS7974")
        # ADB-mode appends BS9991 *after* NIST per legacy add_refs_in_order.
        assert order.index("BS9991") > order.index("NIST")

    def test_fixed_tail_present(self) -> None:
        order = _ref_order_for("BS9991")
        for ref in ("BS1366_2", "BS5839_1", "PD7974_6", "BS12101_6", "SPFE", "SCA_2", "PD7974_1", "BS9251", "BRE_1"):
            assert ref in order
