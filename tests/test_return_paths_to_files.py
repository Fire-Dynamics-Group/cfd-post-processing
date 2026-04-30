"""Tests for return_paths_to_files's nested-folder picking.

Real-world Finchley case: a scenario directory contains both the PyroSim
*project* folder (just .fds / .pyrofloors / .psm.zip / etc.) AND the
`_FDS`-suffixed *run* folder (which holds the devc.csv and hrr.csv).
The helper must pick the folder that actually contains the FDS output
data, not just the first one alphabetically.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from helper_functions import return_paths_to_files


def _touch(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_picks_nested_folder_that_has_devc_and_hrr(tmp_path: Path) -> None:
    # Real Finchley shape:
    #   FS2_Rerun/
    #     0406_..._FSA/                            (PyroSim project, no CSVs)
    #       0406_..._FSA.fds
    #     0406_..._FSA.fds_1777..._FDS/            (FDS run output, has CSVs)
    #       0406_..._FSA.fds
    #       0406_..._FSA_devc.csv
    #       0406_..._FSA_hrr.csv
    scenario_root = tmp_path / "FS2_Rerun"
    project = scenario_root / "0406_Finchley_FS2_Plot84_FSA"
    fds_run = scenario_root / "0406_Finchley_FS2_Plot84_FSA.fds_1777479976394_FDS"

    _touch(project / "0406_Finchley_FS2_Plot84_FSA.fds")
    _touch(fds_run / "0406_Finchley_FS2_Plot84_FSA.fds")
    _touch(fds_run / "0406_Finchley_FS2_Plot84_FSA_devc.csv")
    _touch(fds_run / "0406_Finchley_FS2_Plot84_FSA_hrr.csv")

    hrr, scen_dir, fds, devc, errors = return_paths_to_files(
        scenario_name="FS2_Rerun",
        dir_path=str(tmp_path),
        new_folder_structure=True,
    )

    assert errors == [], f"expected no errors, got: {errors}"
    assert Path(scen_dir) == fds_run
    assert Path(hrr) == fds_run / "0406_Finchley_FS2_Plot84_FSA_hrr.csv"
    assert Path(devc) == fds_run / "0406_Finchley_FS2_Plot84_FSA_devc.csv"
    assert Path(fds) == fds_run / "0406_Finchley_FS2_Plot84_FSA.fds"


def test_single_nested_folder_with_data_still_works(tmp_path: Path) -> None:
    """The existing happy path — one nested run folder with all three files —
    must keep working after the picker changes."""
    scenario_root = tmp_path / "FS1"
    fds_run = scenario_root / "FS1_run_FDS"
    _touch(fds_run / "FS1.fds")
    _touch(fds_run / "FS1_devc.csv")
    _touch(fds_run / "FS1_hrr.csv")

    hrr, scen_dir, fds, devc, errors = return_paths_to_files(
        scenario_name="FS1",
        dir_path=str(tmp_path),
        new_folder_structure=True,
    )

    assert errors == []
    assert Path(scen_dir) == fds_run


def test_no_nested_folder_with_data_falls_back_and_reports(tmp_path: Path) -> None:
    """When *no* nested folder contains both devc.csv and hrr.csv, the
    helper falls back to the first nested folder (legacy behavior) and
    surfaces "no devc/hrr file" errors so the run is skipped."""
    scenario_root = tmp_path / "FS_Broken"
    only_project = scenario_root / "FS_Broken_project"
    _touch(only_project / "FS_Broken.fds")  # no devc, no hrr

    hrr, scen_dir, fds, devc, errors = return_paths_to_files(
        scenario_name="FS_Broken",
        dir_path=str(tmp_path),
        new_folder_structure=True,
    )

    assert any("devc" in e for e in errors)
    assert any("hrr" in e for e in errors)


def test_data_directly_in_scenario_folder_no_nesting(tmp_path: Path) -> None:
    """When the user's scenario folder contains the .fds/devc/hrr files
    directly (no nested run folder), the helper should not descend."""
    scenario_root = tmp_path / "FS_Flat"
    _touch(scenario_root / "FS_Flat.fds")
    _touch(scenario_root / "FS_Flat_devc.csv")
    _touch(scenario_root / "FS_Flat_hrr.csv")

    hrr, scen_dir, fds, devc, errors = return_paths_to_files(
        scenario_name="FS_Flat",
        dir_path=str(tmp_path),
        new_folder_structure=True,
    )

    assert errors == []
    assert Path(scen_dir) == scenario_root
