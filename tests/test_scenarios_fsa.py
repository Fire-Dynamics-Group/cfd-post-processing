"""End-to-end tests for the FSA branch of scenarios_object.create_scenario_object.

Background
----------
Real Finchley FSA scenarios ship corridor / lobby / cc_* sensors alongside
stair sensors, but the FSA branch in scenarios_object.py only iterates stair
sensors and FSA-distance-tagged sensors. As a result `worst_condition` ends
up as just {"stair_temp": ..., "stair_vis": ...} even though the report
needs corridor/lobby data too.

These tests pin down the desired behaviour: every non-stair temp/vis prefix
in the devc CSV produces an entry in `worst_condition`, mirroring the MoE
prefix-discovery loop the same function already uses for the
firefighting==False branch.

Strategy
--------
Drive `create_scenario_object` against a synthetic FDS scenario folder.
External-facing helpers that parse the FDS file (door opening times,
venting, sprinklers) are monkeypatched to safe defaults so the test can
focus on the worst_condition extraction. The devc CSV is real and is read
by production code via read_from_csv_skip_first_row.
"""
import os
from pathlib import Path

import pytest


# --- Fixture builders --------------------------------------------------------

def _write_devc_csv(path, header, rows):
    """Write a devc CSV in the FDS output format that production code reads
    via read_from_csv_skip_first_row (skips first row as units row, second
    row is header)."""
    units = ["s"] + ["C"] * (len(header) - 1)
    with open(path, "w", newline="") as f:
        f.write(",".join(units) + "\n")
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")


def _write_minimal_fds(path):
    """Bare-bones FDS file. The real parsing helpers are monkeypatched in
    the test; this just needs to exist on disk because the production code
    builds a path to it via return_paths_to_files."""
    with open(path, "w") as f:
        f.write("&HEAD CHID='test', TITLE='synthetic FSA fixture' /\n")
        f.write("&TIME T_END=300.0 /\n")
        f.write("&TAIL /\n")


def _build_scenario_dir(root, scenario_name, header, rows):
    """Build the folder structure return_paths_to_files expects when invoked
    with new_folder_structure=True: <root>/<scenario_name>/ with the FDS
    file and devc CSV directly inside.
    """
    scen_dir = root / scenario_name
    scen_dir.mkdir(parents=True, exist_ok=True)
    fds_path = scen_dir / f"{scenario_name}.fds"
    devc_path = scen_dir / f"{scenario_name}_devc.csv"
    hrr_path = scen_dir / f"{scenario_name}_hrr.csv"
    _write_minimal_fds(fds_path)
    _write_devc_csv(devc_path, header, rows)
    # write a no-op hrr (production return_paths_to_files looks for one)
    with open(hrr_path, "w") as f:
        f.write("s,kW\n")
        f.write("Time,HRR\n")
        f.write("0.0,0.0\n")
    return scen_dir


@pytest.fixture
def fsa_safe_defaults(monkeypatch):
    """Replace FDS-parsing helpers so the test never touches the real
    parsers (which expect concrete &VENT, &HOLE, etc. constructs).

    Patches:
      - find_door_opening_times -> {opening_apartment: 0, closing: None, ...}
      - find_venting_from_fds   -> all-zeros / empty
      - is_sprinklered          -> False

    These are patched on the scenarios_object module because that's where
    create_scenario_object resolves the names from (imports done at module
    load).
    """
    import scenarios_object as so

    def fake_door_opening_times(path_to_file):
        return {
            "opening_apartment": 0,
            "closing_apartment": None,
            "opening_stair": 0,
            "closing_stair": None,
        }

    def fake_find_venting(path_to_file):
        # return shape matches scen_object_helper_functions.find_venting_from_fds
        # (extract_rate_list, supply_rate_list, aov_area, extract_count,
        #  supply_count, natural_inlet_list)
        return [], [], 0, 0, 0, []

    def fake_is_sprinklered(path_to_file):
        return False

    monkeypatch.setattr(
        so, "find_door_opening_times_with_close_defaults", fake_door_opening_times
    )
    monkeypatch.setattr(so, "find_venting_from_fds", fake_find_venting)
    monkeypatch.setattr(so, "is_sprinklered", fake_is_sprinklered)
    return monkeypatch


# --- Tests -------------------------------------------------------------------

def test_fsa_scenario_with_cc_and_lobby_prefixes_populates_worst_condition(
    tmp_path, fsa_safe_defaults, monkeypatch
):
    """FS1-style FSA: cc_*, Lobby_*, stair_* sensors. The FSA branch must
    surface a worst_condition entry for each non-stair temp/vis prefix as
    well as the stair pair."""
    from scenarios_object import create_scenario_object

    scenario_name = "0406_Finchley_FS1_Plot80_FSA"
    header = [
        "Time",
        # cc_temp_*
        "cc_temp_1", "cc_temp_2", "cc_temp_3",
        # Lobby_temp_*
        "Lobby_temp_1", "Lobby_temp_2", "Lobby_temp_3",
        # stair_temp_* (zero-padded, like real FS1)
        "stair_temp_01", "stair_temp_02", "stair_temp_03", "stair_temp_04",
        # cc_vis_*
        "cc_vis_1", "cc_vis_2", "cc_vis_3",
        # Lobby_vis_*
        "Lobby_vis_1", "Lobby_vis_2", "Lobby_vis_3",
        # stair_vis_*
        "stair_vis_01", "stair_vis_02", "stair_vis_03", "stair_vis_04",
        # pres / vel - present so they're discoverable but should NOT appear in worst_condition
        "cc_pres_1", "Lobby_pres_1", "stair_pres_1", "stair_pres_2",
    ]
    rows = [
        [0.0,
         20.0, 21.0, 22.0,        # cc_temp
         23.0, 24.0, 25.0,        # Lobby_temp
         18.0, 19.0, 20.0, 21.0,  # stair_temp
         30.0, 28.0, 26.0,        # cc_vis (start clear)
         29.0, 27.0, 25.0,        # Lobby_vis
         30.0, 30.0, 30.0, 30.0,  # stair_vis
         -1.0, -2.0, 0.0, 0.0],
        [60.0,
         100.0, 110.0, 120.0,     # cc_temp peaks
         80.0, 90.0, 95.0,        # Lobby_temp peaks
         40.0, 45.0, 50.0, 55.0,  # stair_temp peaks
         5.0, 6.0, 7.0,           # cc_vis (worst min in row 1)
         8.0, 9.0, 10.0,          # Lobby_vis worst min
         28.0, 27.0, 26.0, 25.0,  # stair_vis worst (min)
         -10.0, -11.0, -5.0, -6.0],
        [120.0,
         50.0, 55.0, 60.0,
         40.0, 45.0, 50.0,
         30.0, 32.0, 34.0, 36.0,
         10.0, 11.0, 12.0,
         15.0, 16.0, 17.0,
         29.0, 28.0, 27.0, 26.0,
         -2.0, -3.0, -1.0, -2.0],
    ]
    _build_scenario_dir(tmp_path, scenario_name, header, rows)

    scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios, error_list = (
        create_scenario_object(path_to_directory=str(tmp_path))
    )

    assert error_list == [] or error_list is None or len(error_list) == 0
    assert scenario_name in scenario_names
    assert scenario_name in FSA_scenarios

    scen = scenarios_object[scenario_name]
    wc = scen["worst_condition"]

    # Stair entries must still be present (preserve existing FSA semantics)
    assert "stair_temp" in wc
    assert "stair_vis" in wc

    # NEW behaviour: corridor / lobby prefixes surfaced too
    assert "cc_temp" in wc, f"cc_temp missing from worst_condition: {wc}"
    assert "cc_vis" in wc, f"cc_vis missing from worst_condition: {wc}"
    assert "Lobby_temp" in wc, f"Lobby_temp missing from worst_condition: {wc}"
    assert "Lobby_vis" in wc, f"Lobby_vis missing from worst_condition: {wc}"

    # All values must be floats, not lists / not NaN
    for key, val in wc.items():
        assert isinstance(val, float), f"{key} -> {val!r} is not a float"
        assert val == val, f"{key} -> NaN"

    # pres / vel must NOT appear in worst_condition (matching MoE branch)
    assert "cc_pres" not in wc
    assert "stair_pres" not in wc
    assert "Lobby_pres" not in wc

    # tenability stays {2m: [], 4m: [], 15m: []} since fixture has no FSA
    # distance-tagged sensors
    assert scen["tenability"] == {"2m": [], "4m": [], "15m": []}


def test_fsa_scenario_with_corridor_and_lobby_prefixes_populates_worst_condition(
    tmp_path, fsa_safe_defaults, monkeypatch
):
    """FS2-style FSA: corridor_1_*, lobby_1_* (lowercase), stair_* sensors."""
    from scenarios_object import create_scenario_object

    scenario_name = "0406_Finchley_FS2_Plot84_FSA"
    header = [
        "Time",
        "corridor_1_temp_1", "corridor_1_temp_2", "corridor_1_temp_3",
        "lobby_1_temp_1", "lobby_1_temp_2",
        "stair_temp_1", "stair_temp_2", "stair_temp_3", "stair_temp_4",
        "corridor_1_vis_1", "corridor_1_vis_2",
        "lobby_1_vis_1", "lobby_1_vis_2",
        "stair_vis_1", "stair_vis_2", "stair_vis_3", "stair_vis_4",
        "corridor_1_pres_1", "lobby_1_pres_1", "stair_pres_1", "stair_pres_2",
    ]
    rows = [
        [0.0,
         20.0, 21.0, 22.0,
         23.0, 24.0,
         18.0, 19.0, 20.0, 21.0,
         30.0, 28.0,
         29.0, 27.0,
         30.0, 30.0, 30.0, 30.0,
         -1.0, -2.0, 0.0, 0.0],
        [60.0,
         110.0, 120.0, 130.0,
         95.0, 100.0,
         50.0, 55.0, 60.0, 65.0,
         5.0, 6.0,
         7.0, 8.0,
         28.0, 27.0, 26.0, 25.0,
         -10.0, -11.0, -5.0, -6.0],
        [120.0,
         60.0, 65.0, 70.0,
         50.0, 55.0,
         40.0, 42.0, 44.0, 46.0,
         12.0, 13.0,
         14.0, 15.0,
         29.0, 28.0, 27.0, 26.0,
         -2.0, -3.0, -1.0, -2.0],
    ]
    _build_scenario_dir(tmp_path, scenario_name, header, rows)

    scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios, error_list = (
        create_scenario_object(path_to_directory=str(tmp_path))
    )

    assert error_list == [] or error_list is None or len(error_list) == 0
    assert scenario_name in scenario_names
    assert scenario_name in FSA_scenarios

    scen = scenarios_object[scenario_name]
    wc = scen["worst_condition"]

    # Stair entries still present
    assert "stair_temp" in wc
    assert "stair_vis" in wc

    # NEW: area-prefix keys present
    assert "corridor_1_temp" in wc, f"corridor_1_temp missing: {wc}"
    assert "corridor_1_vis" in wc, f"corridor_1_vis missing: {wc}"
    assert "lobby_1_temp" in wc, f"lobby_1_temp missing: {wc}"
    assert "lobby_1_vis" in wc, f"lobby_1_vis missing: {wc}"

    for key, val in wc.items():
        assert isinstance(val, float), f"{key} -> {val!r} is not a float"
        assert val == val, f"{key} -> NaN"

    # tenability stays empty per fixture
    assert scen["tenability"] == {"2m": [], "4m": [], "15m": []}
