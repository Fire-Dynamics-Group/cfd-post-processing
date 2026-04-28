"""Regression tests for helper_functions.find_worst_case_column_name.

These cover two bugs hit by real FDS jobs:

    Bug A: Zero-padded stair sensors (stair_temp_01..08) caused IndexError
           because the index-probing loop searched for `_1`, `_2`... and
           stair_temp_01 does not end with `_1`.

    Bug B: Mixed sets that contain *some* stair columns
           (e.g. corridor_1_pres_* + lobby_1_pres_* + stair_pres_*)
           triggered stair-split via `any("stair" in c)` then failed
           enumerating gaps in 70 columns.

The function's intended behaviour (from the in-source TODOs at L109-110):

    - "Stair mode" produces TWO worst-case columns (worst_case + worst_case_b)
      by sorting the stair sensors and bisecting them — one per safety zone.
    - "Stair mode" should engage ONLY when ALL columns are stair sensors.
      Mixed sets fall through to a single worst_case computation.
    - Sorting must tolerate zero-padded device numbers and gaps in
      numbering (real FDS jobs have both).
"""

import pandas as pd
import pytest

from helper_functions import find_worst_case_column_name


def _make_df(col_to_values):
    """Build a small DataFrame from a {column_name: [values_per_row]} map.

    A leading 'Time' column is included to mimic real devc output.
    All columns must have the same row count.
    """
    n_rows = len(next(iter(col_to_values.values())))
    data = {"Time": [float(i) for i in range(n_rows)]}
    data.update(col_to_values)
    return pd.DataFrame(data)


# --- Bug A: zero-padded stair temps (the live failure on Finchley FS1) -----

def test_zero_padded_stair_temps_split_into_halves():
    # 8 stair sensors, zero-padded. Per-row known values so we can assert
    # both worst_case (max of 01-04) and worst_case_b (max of 05-08).
    cols = {
        "stair_temp_01": [10.0, 11.0],
        "stair_temp_02": [20.0, 21.0],
        "stair_temp_03": [30.0, 31.0],
        "stair_temp_04": [40.0, 41.0],   # max of lower half each row
        "stair_temp_05": [15.0, 16.0],
        "stair_temp_06": [25.0, 26.0],
        "stair_temp_07": [35.0, 36.0],
        "stair_temp_08": [45.0, 46.0],   # max of upper half each row
    }
    df = _make_df(cols)
    column_names = list(cols.keys())

    result = find_worst_case_column_name(
        worst_case_max_or_min="max",
        column_names=column_names,
        df=df,
    )

    assert "worst_case" in result.columns
    assert "worst_case_b" in result.columns
    assert list(result["worst_case"]) == [40.0, 41.0]
    assert list(result["worst_case_b"]) == [45.0, 46.0]


# --- Bug B: mixed corridor + lobby + stair pres set ------------------------

def test_mixed_pres_set_does_not_split_into_halves():
    # 5 columns. Includes 'stair' substring in 2 of them but is NOT all-stair,
    # so this should fall through to a single worst_case computation.
    cols = {
        "corridor_1_pres_1": [1.0, 2.0],
        "corridor_1_pres_2": [3.0, 4.0],
        "lobby_1_pres_1":    [-5.0, -6.0],   # min each row
        "stair_pres_1":      [0.5, 0.5],
        "stair_pres_2":      [0.7, 0.8],
    }
    df = _make_df(cols)
    column_names = list(cols.keys())

    result = find_worst_case_column_name(
        worst_case_max_or_min="min",
        column_names=column_names,
        df=df,
    )

    assert "worst_case" in result.columns
    assert "worst_case_b" not in result.columns
    assert list(result["worst_case"]) == [-5.0, -6.0]


# --- Stair with non-zero-padded legacy names -------------------------------

def test_stair_legacy_unpadded_names_split_into_halves():
    cols = {
        "stair_temp_1": [10.0, 11.0],
        "stair_temp_2": [20.0, 21.0],
        "stair_temp_3": [30.0, 31.0],
        "stair_temp_4": [40.0, 41.0],   # max of 1-4
        "stair_temp_5": [15.0, 16.0],
        "stair_temp_6": [25.0, 26.0],
        "stair_temp_7": [35.0, 36.0],
        "stair_temp_8": [45.0, 46.0],   # max of 5-8
    }
    df = _make_df(cols)
    column_names = list(cols.keys())

    result = find_worst_case_column_name(
        worst_case_max_or_min="max",
        column_names=column_names,
        df=df,
    )

    assert list(result["worst_case"]) == [40.0, 41.0]
    assert list(result["worst_case_b"]) == [45.0, 46.0]


# --- Stair with gaps in numbering ------------------------------------------

def test_stair_with_gaps_sorts_by_trailing_int_then_bisects():
    # Numbering gaps: 04 and 07 are missing. Sorted by trailing int gives
    # [01, 02, 03, 05, 06, 08]. Half = 3, so:
    #   worst_case   = max across 01, 02, 03
    #   worst_case_b = max across 05, 06, 08
    cols = {
        "stair_temp_01": [10.0, 11.0],
        "stair_temp_02": [20.0, 21.0],
        "stair_temp_03": [30.0, 31.0],   # max of first half
        "stair_temp_05": [15.0, 16.0],
        "stair_temp_06": [25.0, 26.0],
        "stair_temp_08": [45.0, 46.0],   # max of second half
    }
    df = _make_df(cols)
    # Pass them in a deliberately scrambled order to prove sort happens.
    column_names = ["stair_temp_05", "stair_temp_01", "stair_temp_08",
                    "stair_temp_03", "stair_temp_06", "stair_temp_02"]

    result = find_worst_case_column_name(
        worst_case_max_or_min="max",
        column_names=column_names,
        df=df,
    )

    assert list(result["worst_case"]) == [30.0, 31.0]
    assert list(result["worst_case_b"]) == [45.0, 46.0]


# --- Non-stair single set --------------------------------------------------

def test_non_stair_single_worst_case_only():
    cols = {
        "corridor_1_temp_1": [10.0, 11.0],
        "corridor_1_temp_2": [20.0, 21.0],
        "corridor_1_temp_3": [30.0, 31.0],
        "corridor_1_temp_4": [40.0, 41.0],
        "corridor_1_temp_5": [50.0, 51.0],   # row max
    }
    df = _make_df(cols)
    column_names = list(cols.keys())

    result = find_worst_case_column_name(
        worst_case_max_or_min="max",
        column_names=column_names,
        df=df,
    )

    assert "worst_case" in result.columns
    assert "worst_case_b" not in result.columns
    assert list(result["worst_case"]) == [50.0, 51.0]


# --- Empty column_names ----------------------------------------------------

def test_empty_column_names_returns_df_unchanged():
    """Documented behaviour: empty input is a no-op. No worst_case column added,
    no exception. Caller decides whether to filter beforehand."""
    df = _make_df({"corridor_1_temp_1": [1.0, 2.0]})
    original_columns = list(df.columns)

    result = find_worst_case_column_name(
        worst_case_max_or_min="max",
        column_names=[],
        df=df,
    )

    assert "worst_case" not in result.columns
    assert "worst_case_b" not in result.columns
    assert list(result.columns) == original_columns
