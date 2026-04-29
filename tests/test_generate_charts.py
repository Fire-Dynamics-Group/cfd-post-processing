"""Tests for the /generate-charts endpoint (charts-only mode).

Mirrors legacy ``run_only_charts.py``: discover scenario subfolders, resolve
fds/devc/hrr paths, run HRR + DEVC chart generators per scenario, return a
manifest of PNG URLs. The real chart generators are exercised in their own
tests; here we monkeypatch them so this test stays fast and does not need a
heavyweight FDS fixture.
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from pipeline import server


def _stub_chart_funcs(monkeypatch):
    captured: list[tuple[str, str, bool]] = []

    def fake_paths(scenario_name, dir_path, new_folder_structure):
        return (
            f"{dir_path}/{scenario_name}/hrr.csv",
            f"{dir_path}/{scenario_name}",
            f"{dir_path}/{scenario_name}/scen.fds",
            f"{dir_path}/{scenario_name}/devc.csv",
            [],
        )

    def fake_hrr(path_to_fds, path_to_hrr, new_dir_path, firefighting=False):
        captured.append(("hrr", new_dir_path, firefighting))
        with open(os.path.join(new_dir_path, "hrr_chart.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    def fake_devc(path_to_devc, path_to_fds, new_dir_path, firefighting=False):
        captured.append(("devc", new_dir_path, firefighting))
        for name in ("devc_temperature_chart.png", "devc_visibility_chart.png"):
            with open(os.path.join(new_dir_path, name), "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(server, "return_paths_to_files", fake_paths)
    monkeypatch.setattr(server, "run_hrr_charts", fake_hrr)
    monkeypatch.setattr(server, "run_devc_charts", fake_devc)
    return captured


def test_generate_charts_returns_manifest_per_scenario(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "FS1_FSA").mkdir()
    (project / "FS2_MOE").mkdir()

    captured = _stub_chart_funcs(monkeypatch)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))

    client = TestClient(server.create_app())
    resp = client.post(
        "/generate-charts",
        json={"PATH": str(project), "PROJECT_NAME": "Test"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["project_name"] == "Test"
    assert body.get("job_id")

    scenarios_by_name = {s["name"]: s for s in body["scenarios"]}
    assert sorted(scenarios_by_name) == ["FS1_FSA", "FS2_MOE"]

    fsa = scenarios_by_name["FS1_FSA"]
    filenames = sorted(c["filename"] for c in fsa["charts"])
    assert filenames == [
        "devc_temperature_chart.png",
        "devc_visibility_chart.png",
        "hrr_chart.png",
    ]
    for chart in fsa["charts"]:
        assert chart["url"] == f"/charts/{body['job_id']}/FS1_FSA/{chart['filename']}"

    # Firefighting flag must follow the "FSA in name" rule (mirrors run_CFD_charts).
    fsa_flags = [c[2] for c in captured if "FS1_FSA" in c[1]]
    moe_flags = [c[2] for c in captured if "FS2_MOE" in c[1]]
    assert fsa_flags and all(flag is True for flag in fsa_flags)
    assert moe_flags and all(flag is False for flag in moe_flags)


def test_generate_charts_serves_pngs_via_static_mount(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "FS1_FSA").mkdir()

    _stub_chart_funcs(monkeypatch)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))

    client = TestClient(server.create_app())
    resp = client.post(
        "/generate-charts",
        json={"PATH": str(project), "PROJECT_NAME": "Test"},
    )
    assert resp.status_code == 200
    chart_url = resp.json()["scenarios"][0]["charts"][0]["url"]

    img_resp = client.get(chart_url)
    assert img_resp.status_code == 200
    assert img_resp.content.startswith(b"\x89PNG")


def test_generate_charts_400_when_path_missing(tmp_path, monkeypatch):
    _stub_chart_funcs(monkeypatch)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))

    client = TestClient(server.create_app())
    resp = client.post(
        "/generate-charts",
        json={"PATH": str(tmp_path / "does-not-exist"), "PROJECT_NAME": "Test"},
    )
    assert resp.status_code == 400


def test_generate_charts_skips_subdirs_with_missing_files(tmp_path, monkeypatch):
    """Real-world fixture (Finchley) has a sibling 'FS2_Rerun' folder next to
    valid scenario dirs. ``return_paths_to_files`` reports an error_list
    naming the missing .fds/hrr/devc files for it. The endpoint must skip
    that subdir (no chart generation, no crash) and surface the errors in
    the response so the UI can show them.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "FS1_FSA").mkdir()
    (project / "FS2_Rerun").mkdir()

    captured: list[tuple[str, str, bool]] = []

    def fake_paths(scenario_name, dir_path, new_folder_structure):
        if scenario_name == "FS2_Rerun":
            return (
                f"{dir_path}/{scenario_name}/error",
                f"{dir_path}/{scenario_name}",
                f"{dir_path}/{scenario_name}/error",
                f"{dir_path}/{scenario_name}/error",
                [
                    f"No fds file found in {dir_path}/{scenario_name}",
                    f"No devc file found in {dir_path}/{scenario_name}",
                    f"No hrr file found in {dir_path}/{scenario_name}",
                ],
            )
        return (
            f"{dir_path}/{scenario_name}/hrr.csv",
            f"{dir_path}/{scenario_name}",
            f"{dir_path}/{scenario_name}/scen.fds",
            f"{dir_path}/{scenario_name}/devc.csv",
            [],
        )

    def fake_hrr(path_to_fds, path_to_hrr, new_dir_path, firefighting=False):
        captured.append(("hrr", new_dir_path, firefighting))
        with open(os.path.join(new_dir_path, "hrr_chart.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    def fake_devc(path_to_devc, path_to_fds, new_dir_path, firefighting=False):
        captured.append(("devc", new_dir_path, firefighting))
        with open(os.path.join(new_dir_path, "devc_chart.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(server, "return_paths_to_files", fake_paths)
    monkeypatch.setattr(server, "run_hrr_charts", fake_hrr)
    monkeypatch.setattr(server, "run_devc_charts", fake_devc)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))

    client = TestClient(server.create_app())
    resp = client.post(
        "/generate-charts",
        json={"PATH": str(project), "PROJECT_NAME": "Test"},
    )

    assert resp.status_code == 200
    body = resp.json()

    scenarios_by_name = {s["name"]: s for s in body["scenarios"]}
    assert list(scenarios_by_name) == ["FS1_FSA"], (
        "FS2_Rerun should be skipped: it has no .fds/hrr/devc files"
    )

    # Errors from the bad subdir surfaced in the response.
    assert any("FS2_Rerun" in e for e in body["errors"])

    # No chart helpers invoked for the bad subdir.
    captured_dirs = {entry[1] for entry in captured}
    assert all("FS2_Rerun" not in d for d in captured_dirs)
