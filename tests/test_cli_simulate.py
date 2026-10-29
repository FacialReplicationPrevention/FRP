"""`frp simulate` command: end-to-end simulated pipeline, exit codes and safe output."""

from __future__ import annotations

import subprocess
import sys

import pytest

from frp.cli import EXIT_INVALID, EXIT_OK, EXIT_OUTPUT, EXIT_USAGE, main
from frp.reporting import SIMULATED_BANNER
from tests.conftest import EXAMPLE_MANIFEST


def _run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_simulate_writes_reports(capsys, tmp_path):
    report_dir = tmp_path / "reports"
    code, out, err = _run(
        capsys, "simulate", str(EXAMPLE_MANIFEST), "--report-dir", str(report_dir)
    )
    assert code == EXIT_OK, err
    assert err == ""
    assert out.startswith(SIMULATED_BANNER)
    assert "Planned runs: 24" in out
    assert "scenario mixed" in out
    assert str(report_dir) not in out
    assert (report_dir / "report.md").read_text(encoding="utf-8").count(SIMULATED_BANNER) == 1
    assert (report_dir / "summary.csv").exists()


def test_simulate_is_byte_for_byte_reproducible(capsys, tmp_path):
    for name in ("one", "two"):
        args = ("simulate", str(EXAMPLE_MANIFEST), "--report-dir", str(tmp_path / name))
        assert _run(capsys, *args)[0] == EXIT_OK
    for filename in ("report.md", "summary.csv"):
        assert (tmp_path / "one" / filename).read_bytes() == (
            tmp_path / "two" / filename
        ).read_bytes()


def test_simulate_refuses_to_overwrite_without_flag(capsys, tmp_path):
    args = ("simulate", str(EXAMPLE_MANIFEST), "--report-dir", str(tmp_path))
    assert _run(capsys, *args)[0] == EXIT_OK
    code, out, err = _run(capsys, *args)
    assert code == EXIT_OUTPUT
    assert out == ""
    assert "--overwrite" in err
    assert str(tmp_path) not in err
    assert _run(capsys, *args, "--overwrite")[0] == EXIT_OK


def test_simulate_scenario_selection(capsys, tmp_path):
    code, out, _ = _run(
        capsys,
        "simulate",
        str(EXAMPLE_MANIFEST),
        "--report-dir",
        str(tmp_path),
        "--scenario",
        "failed-run",
    )
    assert code == EXIT_OK
    assert "scenario failed-run" in out
    assert "scenario `failed-run`" in (tmp_path / "report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "extra",
    [[], ["--report-dir"], ["--report-dir", "x", "--scenario", "no-such-scenario"]],
)
def test_simulate_usage_errors(capsys, extra):
    code, _, _ = _run(capsys, "simulate", str(EXAMPLE_MANIFEST), *extra)
    assert code == EXIT_USAGE


def test_simulate_invalid_manifest(capsys, manifest_data, write_manifest, tmp_path):
    manifest_data["prompts"][0]["text"] = {"private": "LEAK-CHECK-VALUE"}
    path = write_manifest(manifest_data)
    code, out, err = _run(capsys, "simulate", str(path), "--report-dir", str(tmp_path / "r"))
    assert code == EXIT_INVALID
    assert out == ""
    assert "frp: invalid manifest:" in err
    assert "LEAK-CHECK-VALUE" not in err
    assert not (tmp_path / "r").exists()


def test_simulate_unwritable_report_dir(capsys, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    code, _, err = _run(
        capsys, "simulate", str(EXAMPLE_MANIFEST), "--report-dir", str(blocker / "sub")
    )
    assert code == EXIT_OUTPUT
    assert "cannot write reports" in err
    assert str(tmp_path) not in err


def test_simulate_module_entry_point(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "frp",
            "simulate",
            str(EXAMPLE_MANIFEST),
            "--report-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    assert result.returncode == EXIT_OK, result.stderr
    assert SIMULATED_BANNER in result.stdout


def test_pipeline_modules_do_not_import_heavy_ml_dependencies():
    code = (
        "import sys, frp.cli, frp.interfaces, frp.results, frp.pipeline, frp.simulation, "
        "frp.aggregation, frp.reporting; "
        "heavy = {'torch', 'numpy', 'cv2', 'PIL', 'transformers', 'diffusers', 'insightface', "
        "'onnxruntime', 'scipy', 'pandas'}; "
        "print(sorted(heavy & set(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == "[]"
