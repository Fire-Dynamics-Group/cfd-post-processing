"""Resource lookup precedence for the bundled sidecar.

PR 3 decision #2: PyInstaller `datas` is the single source of truth for
bundled resources. The orchestrator's `_resolve_template_path` and
`_resolve_references_csv` must walk:

    1. ``sys._MEIPASS`` (set inside PyInstaller bundles)
    2. ``Path(sys.executable).parent`` (next to the bundled exe)
    3. dev fallback: ``Path(__file__).resolve().parents[2]`` (project root)

These tests pin the precedence by monkeypatching `sys._MEIPASS` /
`sys.executable` at runtime — there is no way to exercise the bundled
paths from a test otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipeline.services import report as report_mod


@pytest.fixture
def clear_meipass(monkeypatch):
    """Ensure sys._MEIPASS is unset for the duration of the test.

    Tests run from a normal Python interpreter so this is usually a no-op,
    but be explicit so the assertions don't depend on a clean global env.
    """
    if hasattr(sys, "_MEIPASS"):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)


class TestResolveTemplatePath:
    def test_meipass_wins_over_other_tiers(self, tmp_path, monkeypatch):
        meipass = tmp_path / "meipass"
        meipass.mkdir()
        target = meipass / "Template CFD Report.docx"
        target.write_bytes(b"")
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

        result = report_mod._resolve_template_path()

        assert result == target

    def test_executable_parent_when_meipass_unset(
        self, tmp_path, monkeypatch, clear_meipass
    ):
        exe_dir = tmp_path / "bin"
        exe_dir.mkdir()
        target = exe_dir / "Template CFD Report.docx"
        target.write_bytes(b"")
        fake_exe = exe_dir / "pipeline-server.exe"
        fake_exe.write_bytes(b"")
        monkeypatch.setattr(sys, "executable", str(fake_exe))

        result = report_mod._resolve_template_path()

        assert result == target

    def test_dev_fallback_resolves_to_project_root(self, clear_meipass):
        # `sys.executable` is the test runner's Python — does not have
        # the template next to it — so the dev fallback (parents[2] of
        # report.py == project root) must catch the lookup.
        result = report_mod._resolve_template_path()

        assert result.name == "Template CFD Report.docx"
        assert result.exists()


class TestResolveReferencesCsv:
    def test_meipass_wins_over_other_tiers(self, tmp_path, monkeypatch):
        meipass = tmp_path / "meipass"
        meipass.mkdir()
        target = meipass / "references.csv"
        target.write_text("id,title\n", encoding="utf-8")
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

        result = report_mod._resolve_references_csv()

        assert result == target

    def test_executable_parent_when_meipass_unset(
        self, tmp_path, monkeypatch, clear_meipass
    ):
        exe_dir = tmp_path / "bin"
        exe_dir.mkdir()
        target = exe_dir / "references.csv"
        target.write_text("id,title\n", encoding="utf-8")
        fake_exe = exe_dir / "pipeline-server.exe"
        fake_exe.write_bytes(b"")
        monkeypatch.setattr(sys, "executable", str(fake_exe))

        result = report_mod._resolve_references_csv()

        assert result == target

    def test_dev_fallback_resolves_to_project_root(self, clear_meipass):
        result = report_mod._resolve_references_csv()

        assert result.name == "references.csv"
        assert result.exists()
