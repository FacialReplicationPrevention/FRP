from __future__ import annotations

import json
import subprocess
import sys

import pytest

from frp.cli import EXIT_INVALID, EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, NOTICE, main
from tests.conftest import EXAMPLE_MANIFEST

SYNTHETIC_PROMPT_TEXT = "softly lit room"


def _run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_dry_run_text_output(capsys):
    code, out, err = _run(capsys, "plan", str(EXAMPLE_MANIFEST), "--dry-run")
    assert code == EXIT_OK
    assert err == ""
    assert out.startswith(NOTICE)
    assert "no scientific outcome has been measured" in out
    assert "Trial groups: 6  Planned runs: 24" in out
    assert "Execution readiness: NOT READY" in out
    assert "FRP-EXP-002-SYNTHETIC-EXAMPLE-G0006-D" in out


def test_dry_run_redacts_pseudonyms_and_never_prints_prompt_text(capsys):
    for fmt in ("text", "json"):
        code, out, _ = _run(capsys, "plan", str(EXAMPLE_MANIFEST), "--dry-run", "--format", fmt)
        assert code == EXIT_OK
        assert "SYN-00" not in out
        assert "identity-01" in out
        assert SYNTHETIC_PROMPT_TEXT not in out
        assert str(EXAMPLE_MANIFEST.parent) not in out


def test_show_pseudonyms_is_opt_in(capsys):
    code, out, _ = _run(capsys, "plan", str(EXAMPLE_MANIFEST), "--dry-run", "--show-pseudonyms")
    assert code == EXIT_OK
    assert "SYN-001" in out
    assert SYNTHETIC_PROMPT_TEXT not in out


def test_dry_run_json_output(capsys):
    code, out, _ = _run(capsys, "plan", str(EXAMPLE_MANIFEST), "--dry-run", "--format", "json")
    assert code == EXIT_OK
    report = json.loads(out)
    assert report["dry_run"] is True
    assert report["counts"]["planned_runs"] == 24
    assert report["readiness"]["ready_for_execution"] is False
    assert [run["variant"] for run in report["runs"][:4]] == ["A", "B", "C", "D"]
    assert set(report["runs"][0]) == {
        "run_id",
        "group",
        "identity",
        "prompt_id",
        "seed",
        "variant",
        "clip_conditioning",
        "vae_first_frame_conditioning",
    }


def test_execution_without_dry_run_is_refused(capsys):
    code, out, err = _run(capsys, "plan", str(EXAMPLE_MANIFEST))
    assert code == EXIT_USAGE
    assert out == ""
    assert "only --dry-run is supported" in err


def test_invalid_manifest_reports_clear_errors_without_values(
    capsys, manifest_data, write_manifest
):
    manifest_data["seeds"] = [-5]
    manifest_data["variants"] = ["A", "A", "B", "C"]
    manifest_data["prompts"][0]["text"] = {"private": "LEAK-CHECK-VALUE"}
    code, out, err = _run(capsys, "plan", str(write_manifest(manifest_data)), "--dry-run")
    assert code == EXIT_INVALID
    assert out == ""
    assert "frp: invalid manifest:" in err
    assert "seeds.0: Input should be greater than or equal to 0" in err
    assert "duplicate variant(s): A; missing variant(s): D" in err
    assert "LEAK-CHECK-VALUE" not in err


def test_missing_manifest_file(capsys, tmp_path):
    code, _, err = _run(capsys, "plan", str(tmp_path / "nope.yaml"), "--dry-run")
    assert code == EXIT_INVALID
    assert "file not found" in err


def test_require_ready(capsys, ready_manifest_data, write_manifest):
    code, _, err = _run(capsys, "plan", str(EXAMPLE_MANIFEST), "--dry-run", "--require-ready")
    assert code == EXIT_NOT_READY
    assert "not ready for execution" in err

    path = write_manifest(ready_manifest_data)
    code, out, _ = _run(capsys, "plan", str(path), "--dry-run", "--require-ready")
    assert code == EXIT_OK
    assert "all execution fields are set (execution is still not implemented)" in out


@pytest.mark.parametrize("argv", [[], ["plan"], ["plan", "x.yaml", "--format", "xml"]])
def test_usage_errors(capsys, argv):
    code, _, _ = _run(capsys, *argv)
    assert code == EXIT_USAGE


def test_module_entry_point_runs_without_network_or_gpu():
    result = subprocess.run(
        [sys.executable, "-m", "frp", "plan", str(EXAMPLE_MANIFEST), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == EXIT_OK, result.stderr
    assert "Planned runs: 24" in result.stdout


def test_package_does_not_import_heavy_ml_dependencies():
    code = (
        "import sys, frp.cli, frp.planner, frp.manifest; "
        "heavy = {'torch', 'numpy', 'cv2', 'PIL', 'transformers', 'diffusers'}; "
        "print(sorted(heavy & set(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == "[]"
