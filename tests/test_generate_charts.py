"""Tests for the /generate-charts endpoints (charts-only mode, async).

Contract:

- ``POST /generate-charts`` validates the body, kicks off a background
  worker thread, and returns ``202 + {job_id}`` immediately.
- ``GET  /generate-charts/{job_id}`` returns a snapshot of that job's
  state — ``status`` (``running`` / ``completed`` / ``failed``),
  ``project_name``, ``scenarios`` (progressively populated as each
  scenario's charts land on disk), ``scenarios_total`` (the total once
  discovery is done), ``errors`` (any per-scenario errors surfaced by
  ``return_paths_to_files``), and on failure ``error`` / ``traceback``.
- The static mount at ``/charts`` continues to serve PNGs by job id.

Tests stub the heavy chart helpers (``run_hrr_charts``, ``run_devc_charts``,
``return_paths_to_files``) on the ``server`` module so the suite stays
fast and doesn't need a real FDS fixture.
"""
from __future__ import annotations

import os
import threading
import time

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


def _wait_terminal(client, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    body = None
    while time.monotonic() < deadline:
        resp = client.get(f"/generate-charts/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise TimeoutError(
        f"charts job {job_id} did not reach a terminal state in {timeout}s; "
        f"last snapshot={body!r}"
    )


def test_generate_charts_returns_jobid_and_then_completes(tmp_path, monkeypatch):
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

    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert isinstance(job_id, str) and len(job_id) >= 8

    body = _wait_terminal(client, job_id)
    assert body["status"] == "completed"
    assert body["project_name"] == "Test"
    assert body["scenarios_total"] == 2

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
        assert chart["url"] == f"/charts/{job_id}/FS1_FSA/{chart['filename']}"

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
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = _wait_terminal(client, job_id)
    chart_url = body["scenarios"][0]["charts"][0]["url"]

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
    # Validation happens synchronously in the POST handler, before the
    # worker thread starts — the user gets the error inline.
    assert resp.status_code == 400


def test_generate_charts_404_for_unknown_job(tmp_path, monkeypatch):
    _stub_chart_funcs(monkeypatch)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))
    client = TestClient(server.create_app())
    resp = client.get("/generate-charts/does-not-exist")
    assert resp.status_code == 404


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
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = _wait_terminal(client, job_id)
    assert body["status"] == "completed"

    scenarios_by_name = {s["name"]: s for s in body["scenarios"]}
    assert list(scenarios_by_name) == ["FS1_FSA"], (
        "FS2_Rerun should be skipped: it has no .fds/hrr/devc files"
    )
    assert any("FS2_Rerun" in e for e in body["errors"])
    captured_dirs = {entry[1] for entry in captured}
    assert all("FS2_Rerun" not in d for d in captured_dirs)


def test_generate_charts_progressive_visibility(tmp_path, monkeypatch):
    """Snapshots taken between POST and the worker's last write must show
    the in-flight scenarios. Each fake_hrr blocks on a per-scenario
    ``threading.Event`` so the test can release them one at a time and
    observe the registry mid-run.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "FS1_FSA").mkdir()
    (project / "FS2_MOE").mkdir()

    gates: dict[str, threading.Event] = {
        "FS1_FSA": threading.Event(),
        "FS2_MOE": threading.Event(),
    }

    def fake_paths(scenario_name, dir_path, new_folder_structure):
        return (
            f"{dir_path}/{scenario_name}/hrr.csv",
            f"{dir_path}/{scenario_name}",
            f"{dir_path}/{scenario_name}/scen.fds",
            f"{dir_path}/{scenario_name}/devc.csv",
            [],
        )

    def fake_hrr(path_to_fds, path_to_hrr, new_dir_path, firefighting=False):
        name = os.path.basename(new_dir_path)
        # Block until the test releases this scenario.
        assert gates[name].wait(timeout=5.0), f"timed out waiting on gate {name}"
        with open(os.path.join(new_dir_path, "hrr_chart.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    def fake_devc(path_to_devc, path_to_fds, new_dir_path, firefighting=False):
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
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Initial snapshot: discovery has likely completed (scenarios_total=2)
    # but no scenario has finished yet because both fake_hrr calls are
    # gated. Be permissive about exact timing — the only guarantee is
    # that scenarios is empty until we release a gate.
    initial = client.get(f"/generate-charts/{job_id}").json()
    assert initial["status"] == "running"
    assert initial["scenarios"] == []

    # Release FS1_FSA, wait for it to land in the snapshot.
    gates["FS1_FSA"].set()
    deadline = time.monotonic() + 3.0
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = client.get(f"/generate-charts/{job_id}").json()
        names = [s["name"] for s in snapshot["scenarios"]]
        if "FS1_FSA" in names:
            break
        time.sleep(0.02)

    assert snapshot["status"] == "running", (
        f"expected still-running snapshot with FS1_FSA visible, got {snapshot!r}"
    )
    assert [s["name"] for s in snapshot["scenarios"]] == ["FS1_FSA"]
    assert snapshot["scenarios_total"] == 2

    # Release the second scenario; the worker should reach completed.
    gates["FS2_MOE"].set()
    final = _wait_terminal(client, job_id)
    assert final["status"] == "completed"
    assert sorted(s["name"] for s in final["scenarios"]) == ["FS1_FSA", "FS2_MOE"]


def test_generate_charts_failed_status_when_worker_raises(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "FS1_FSA").mkdir()

    def fake_paths(*_args, **_kwargs):
        return ("h", "s", "f", "d", [])

    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(server, "return_paths_to_files", fake_paths)
    monkeypatch.setattr(server, "run_hrr_charts", boom)
    monkeypatch.setattr(server, "run_devc_charts", boom)
    monkeypatch.setattr(server, "CHARTS_BASE", str(tmp_path / "out"))

    client = TestClient(server.create_app())
    resp = client.post(
        "/generate-charts",
        json={"PATH": str(project), "PROJECT_NAME": "Test"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = _wait_terminal(client, job_id)
    assert body["status"] == "failed"
    assert "kaboom" in body["error"]
    assert "RuntimeError" in body["error"]
