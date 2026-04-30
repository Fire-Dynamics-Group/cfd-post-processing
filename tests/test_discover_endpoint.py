"""Tests for POST /discover-charts-scenarios.

The endpoint powers the charts-mode folder picker: the frontend POSTs the
user-selected root and renders the returned scenario list as a checklist.
The work is delegated to ``helper_functions.discover_scenarios``; the
endpoint just validates the path and shapes the response.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pipeline import server


def _make_run(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{folder.name}.fds").write_text("")
    (folder / f"{folder.name}_devc.csv").write_text("")
    (folder / f"{folder.name}_hrr.csv").write_text("")


def test_returns_discovered_scenarios(tmp_path: Path) -> None:
    _make_run(tmp_path / "FS1_FDS")
    _make_run(tmp_path / "FS2_Rerun" / "FS2_FDS")

    client = TestClient(server.create_app())
    resp = client.post(
        "/discover-charts-scenarios", json={"PATH": str(tmp_path)}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [s["id"] for s in body["scenarios"]]
    assert ids == ["FS1_FDS", "FS2_Rerun/FS2_FDS"]
    # Each entry exposes the absolute fds_dir so the frontend can echo it
    # back when posting to /generate-charts.
    for s in body["scenarios"]:
        assert Path(s["fds_dir"]).is_dir()


def test_returns_empty_list_when_root_has_no_scenarios(tmp_path: Path) -> None:
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "readme.txt").write_text("not a run")

    client = TestClient(server.create_app())
    resp = client.post(
        "/discover-charts-scenarios", json={"PATH": str(tmp_path)}
    )

    assert resp.status_code == 200
    assert resp.json() == {"scenarios": []}


def test_400_when_path_does_not_exist(tmp_path: Path) -> None:
    client = TestClient(server.create_app())
    resp = client.post(
        "/discover-charts-scenarios",
        json={"PATH": str(tmp_path / "nope")},
    )
    assert resp.status_code == 400
