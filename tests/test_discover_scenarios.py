"""Tests for discover_scenarios — recursive scenario walker that powers the
charts-mode auto-discover folder picker.

A "scenario folder" is any directory containing both a ``*_devc.csv`` and a
``*_hrr.csv`` file (the same heuristic ``_find_folder_with_run_csvs`` uses).
The walker short-circuits on a scenario: it does not descend into a folder
that already qualifies, so we get O(scenario count) traversal instead of
walking every ``.sf`` / ``.s3d`` boundary file an FDS run produces.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from helper_functions import discover_scenarios


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def _make_run(folder: Path) -> None:
    """Populate a folder with the minimum files that make it a scenario."""
    _touch(folder / f"{folder.name}.fds")
    _touch(folder / f"{folder.name}_devc.csv")
    _touch(folder / f"{folder.name}_hrr.csv")


def test_empty_root_returns_empty_list(tmp_path: Path) -> None:
    assert discover_scenarios(str(tmp_path)) == []


def test_finds_single_top_level_scenario(tmp_path: Path) -> None:
    run = tmp_path / "FS1_run_FDS"
    _make_run(run)

    scenarios = discover_scenarios(str(tmp_path))

    assert len(scenarios) == 1
    s = scenarios[0]
    assert s["id"] == "FS1_run_FDS"
    assert s["label"] == "FS1_run_FDS"
    assert Path(s["fds_dir"]) == run


def test_finds_multiple_top_level_scenarios_sorted(tmp_path: Path) -> None:
    for name in ("FS3_run_FDS", "FS1_run_FDS", "FS2_run_FDS"):
        _make_run(tmp_path / name)

    scenarios = discover_scenarios(str(tmp_path))

    assert [s["id"] for s in scenarios] == [
        "FS1_run_FDS",
        "FS2_run_FDS",
        "FS3_run_FDS",
    ]


def test_finds_nested_scenario(tmp_path: Path) -> None:
    """Real Finchley shape: rerun lives in a wrapper folder one level down."""
    _make_run(tmp_path / "0406_FS1_FSA.fds_1776_FDS")
    _make_run(tmp_path / "0406_FS2_FSA.fds_1776_FDS")
    rerun = tmp_path / "FS2_Rerun" / "0406_FS2_FSA.fds_1777_FDS"
    _make_run(rerun)

    scenarios = discover_scenarios(str(tmp_path))

    ids = [s["id"] for s in scenarios]
    # ids use forward slashes for stability across platforms
    assert ids == [
        "0406_FS1_FSA.fds_1776_FDS",
        "0406_FS2_FSA.fds_1776_FDS",
        "FS2_Rerun/0406_FS2_FSA.fds_1777_FDS",
    ]
    rerun_entry = scenarios[2]
    assert Path(rerun_entry["fds_dir"]) == rerun


def test_short_circuits_does_not_descend_into_scenario(tmp_path: Path) -> None:
    """If a scenario folder happens to contain a sub-sub-folder that also has
    devc.csv + hrr.csv (unusual, but possible from re-runs nested inside an
    output dir), only the *outer* scenario is reported. We treat the first
    qualifying folder along a path as the leaf so we don't descend into the
    gigabytes of .sf / .s3d files inside an FDS output."""
    outer = tmp_path / "outer_FDS"
    _make_run(outer)
    nested = outer / "nested_rerun_FDS"
    _make_run(nested)

    scenarios = discover_scenarios(str(tmp_path))

    assert [s["id"] for s in scenarios] == ["outer_FDS"]


def test_root_itself_is_a_scenario(tmp_path: Path) -> None:
    """User selected the FDS run folder directly. Discovery returns one
    entry for the root itself."""
    leaf = tmp_path / "single_run_FDS"
    _make_run(leaf)

    scenarios = discover_scenarios(str(leaf))

    assert len(scenarios) == 1
    assert scenarios[0]["id"] == ""
    assert scenarios[0]["label"] == "single_run_FDS"
    assert Path(scenarios[0]["fds_dir"]) == leaf


def test_skips_folders_missing_either_csv(tmp_path: Path) -> None:
    """A PyroSim project folder (has .fds but no _devc.csv / _hrr.csv) must
    not be picked up as a scenario."""
    project = tmp_path / "FS1_project"
    project.mkdir()
    _touch(project / "FS1.fds")  # no devc, no hrr

    only_hrr = tmp_path / "partial_FDS"
    _touch(only_hrr / "partial.fds")
    _touch(only_hrr / "partial_hrr.csv")  # missing devc

    real = tmp_path / "real_FDS"
    _make_run(real)

    scenarios = discover_scenarios(str(tmp_path))

    assert [s["id"] for s in scenarios] == ["real_FDS"]


def test_id_uses_forward_slashes_on_all_platforms(tmp_path: Path) -> None:
    """The id is used as a JSON-stable key sent to the frontend; it must
    use forward slashes regardless of OS path separator."""
    nested = tmp_path / "wrapper" / "deeper" / "scen_FDS"
    _make_run(nested)

    scenarios = discover_scenarios(str(tmp_path))

    assert scenarios[0]["id"] == "wrapper/deeper/scen_FDS"
