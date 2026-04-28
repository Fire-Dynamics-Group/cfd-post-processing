"""Tests for flexible DEVC column-prefix detection.

These tests exercise the public helpers that downstream modules
(scenarios_object, hrr_graph) rely on to discover device-column prefixes
in real FDS jobs. They cover three naming families seen in production:

  * legacy:        cc_temp_1, cc_temp_47, cc_FSA_temp_15m
  * mixed-case:    Lobby_temp_15, stair_temp_01
  * prefixed area: corridor_1_temp_1, lobby_1_vis_9
"""
import os
from pathlib import Path

import pandas as pd
import pytest


# -- A. get_column_prefix unit tests -----------------------------------------

@pytest.mark.parametrize(
    "column_name,expected_prefix",
    [
        ("cc_temp_1", "cc_temp_"),
        ("cc_temp_47", "cc_temp_"),
        ("cc_temp_01", "cc_temp_"),
        ("corridor_1_temp_1", "corridor_1_temp_"),
        ("corridor_1_temp_15", "corridor_1_temp_"),
        ("lobby_1_vis_9", "lobby_1_vis_"),
        ("Lobby_temp_15", "Lobby_temp_"),
        ("stair_temp_01", "stair_temp_"),
        ("cc_FSA_temp_2m", "cc_FSA_temp_"),
        ("cc_FSA_temp_15m", "cc_FSA_temp_"),
    ],
)
def test_get_column_prefix_strips_trailing_device_number(column_name, expected_prefix):
    from helper_functions import get_column_prefix

    assert get_column_prefix(column_name) == expected_prefix


# -- B. get_cc_columns unit tests --------------------------------------------

def _df_from_columns(columns):
    """Build a 2-row DataFrame with the requested columns (zeros are fine)."""
    data = {col: [0.0, 0.0] for col in columns}
    return pd.DataFrame(data)


def test_get_cc_columns_fs1_temp_excludes_stair_and_fsa():
    from helper_functions import get_cc_columns

    columns = [
        "Time",
        "cc_temp_1",
        "cc_temp_2",
        "Lobby_temp_1",
        "stair_temp_01",
        "cc_pres_1",
        "cc_vis_1",
        "Lobby_vis_1",
        "cc_FSA_temp_2m",
    ]
    df = _df_from_columns(columns)

    result = get_cc_columns(df, "temp")

    assert sorted(result) == sorted(["cc_temp_1", "cc_temp_2", "Lobby_temp_1"])


def test_get_cc_columns_fs1_vis_excludes_stair_and_fsa():
    from helper_functions import get_cc_columns

    columns = [
        "Time",
        "cc_temp_1",
        "cc_temp_2",
        "Lobby_temp_1",
        "stair_temp_01",
        "cc_pres_1",
        "cc_vis_1",
        "Lobby_vis_1",
        "cc_FSA_temp_2m",
    ]
    df = _df_from_columns(columns)

    result = get_cc_columns(df, "vis")

    assert sorted(result) == sorted(["cc_vis_1", "Lobby_vis_1"])


def test_get_cc_columns_fs2_temp_excludes_stair():
    from helper_functions import get_cc_columns

    columns = [
        "Time",
        "corridor_1_temp_1",
        "corridor_1_temp_2",
        "lobby_1_temp_1",
        "stair_temp_1",
        "corridor_1_vis_1",
    ]
    df = _df_from_columns(columns)

    result = get_cc_columns(df, "temp")

    assert sorted(result) == sorted([
        "corridor_1_temp_1",
        "corridor_1_temp_2",
        "lobby_1_temp_1",
    ])


# -- C. get_worst_case_devc(column_names=...) integration test ---------------

def _write_devc_csv(path, header_row, data_rows, units_row=None):
    """Write a devc CSV in the FDS format that read_from_csv_skip_first_row expects.

    The first row is units (skipped); the second row is the header; remaining
    rows are data.
    """
    if units_row is None:
        units_row = ["s"] + ["C"] * (len(header_row) - 1)
    with open(path, "w", newline="") as f:
        f.write(",".join(units_row) + "\n")
        f.write(",".join(header_row) + "\n")
        for row in data_rows:
            f.write(",".join(str(v) for v in row) + "\n")


def test_get_worst_case_devc_uses_explicit_column_names(tmp_path):
    from helper_functions import get_worst_case_devc

    csv_path = tmp_path / "fs2_devc.csv"
    header = [
        "Time",
        "corridor_1_temp_1",
        "corridor_1_temp_2",
        "corridor_1_temp_3",
        "stair_temp_1",
    ]
    # Per-row max across the three corridor columns is: 30, 80, 55
    rows = [
        [0.0, 20.0, 30.0, 25.0, 200.0],
        [1.0, 70.0, 80.0, 50.0, 200.0],
        [2.0, 55.0, 40.0, 35.0, 200.0],
    ]
    _write_devc_csv(csv_path, header, rows)

    column_names = [
        "corridor_1_temp_1",
        "corridor_1_temp_2",
        "corridor_1_temp_3",
    ]
    result = get_worst_case_devc(
        path_to_file=str(csv_path),
        property="temp",
        firefighting=False,
        column_names=column_names,
    )

    assert "worst_case" in result.columns
    assert list(result["worst_case"]) == [30.0, 80.0, 55.0]


# -- D. End-to-end smoke: scenario object MOE prefix discovery ---------------

def test_scenarios_object_moe_loop_populates_fs2_prefix_keys(tmp_path, monkeypatch):
    """Smoke test mirroring the new MOE worst-case prefix-discovery loop in
    scenarios_object.create_scenario_object. Since wiring up the full
    scenario_object flow requires FDS files and folder layout, we exercise
    the same code path inline using the public helpers.
    """
    from helper_functions import (
        get_column_prefix,
        get_cc_columns,
        get_worst_case_devc,
        find_worst_in_column,
    )

    csv_path = tmp_path / "fs2_devc.csv"
    # Two stair columns: find_worst_case_column_name's stair branch splits the
    # ordered stair list in half (worst_case / worst_case_b), so it needs >=2
    # stair sensors to produce a non-empty worst_case column. Real FDS jobs
    # always ship multiple stair sensors.
    header = [
        "Time",
        "corridor_1_temp_1",
        "corridor_1_temp_2",
        "lobby_1_temp_1",
        "lobby_1_temp_2",
        "stair_temp_1",
        "stair_temp_2",
        "corridor_1_vis_1",
        "lobby_1_vis_1",
    ]
    rows = [
        [0.0, 20.0, 25.0, 22.0, 24.0, 200.0, 210.0, 30.0, 28.0],
        [1.0, 75.0, 80.0, 60.0, 65.0, 250.0, 240.0, 5.0, 8.0],
        [2.0, 50.0, 55.0, 45.0, 40.0, 220.0, 230.0, 10.0, 12.0],
    ]
    _write_devc_csv(csv_path, header, rows)

    # Read the same way the production code does
    from helper_functions import read_from_csv_skip_first_row
    devc_df = read_from_csv_skip_first_row(str(csv_path))

    # ----- Replicate the patched MOE loop from scenarios_object.py ----------
    worst_condition = {}

    seen_prefixes = set()
    for column_name in devc_df.columns:
        if column_name == "Time":
            continue
        prefix = get_column_prefix(column_name)
        col_lower = column_name.lower()
        if not any(param in col_lower for param in ["temp", "vis"]):
            continue
        if "fsa" in col_lower or "sprk" in col_lower:
            continue
        seen_prefixes.add(prefix)

    for prefix in seen_prefixes:
        is_stair = "stair" in prefix.lower()
        is_temp = "temp" in prefix.lower()
        if is_stair:
            condition_key = "stair_temp" if is_temp else "stair_vis"
        else:
            condition_key = prefix.rstrip("_")

        prefix_cols = [c for c in devc_df.columns if c.startswith(prefix)]
        new_df = get_worst_case_devc(
            path_to_file=str(csv_path),
            property=prefix.rstrip("_"),
            firefighting=False,
            column_names=prefix_cols,
        )
        worst_condition[condition_key] = find_worst_in_column(
            df=new_df, column_name="worst_case", parameter=prefix.rstrip("_")
        )

    # Combined backward-compatible cc_temp / cc_vis keys
    for param in ["temp", "vis"]:
        cc_cols = get_cc_columns(devc_df, param)
        if cc_cols:
            new_df = get_worst_case_devc(
                path_to_file=str(csv_path),
                property=param,
                firefighting=False,
                column_names=cc_cols,
            )
            worst_condition[f"cc_{param}"] = find_worst_in_column(
                df=new_df, column_name="worst_case", parameter=param
            )

    # ----- Assertions: keys exist and hold sane non-NaN floats --------------
    # FS2 area-prefix keys must appear (NOT swallowed by buggy prefix
    # extraction that would have produced 'corridor_' instead of
    # 'corridor_1_temp_').
    assert "corridor_1_temp" in worst_condition
    assert "lobby_1_temp" in worst_condition
    assert "corridor_1_vis" in worst_condition
    assert "lobby_1_vis" in worst_condition
    assert "stair_temp" in worst_condition

    # Values are floats (not NaN, not empty).
    for key, val in worst_condition.items():
        assert isinstance(val, float), f"{key} -> {val!r} is not a float"
        assert val == val, f"{key} -> NaN"  # NaN != NaN

    # Sanity: corridor_1_temp worst (max) over the synthetic data is row1 = 80.0
    assert worst_condition["corridor_1_temp"] == 80.0
    # Sanity: corridor_1_vis worst (min) over the synthetic data is row1 = 5.0
    assert worst_condition["corridor_1_vis"] == 5.0
    # Combined cc_temp ignores stair_temp; max across non-stair non-FSA temp
    # cols is 80.0 (corridor_1_temp_2 at t=1)
    assert worst_condition["cc_temp"] == 80.0
