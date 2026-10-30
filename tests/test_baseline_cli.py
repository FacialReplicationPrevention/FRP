"""`frp baseline-plan`: planning only, privacy-safe output, no way to execute."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from frp.cli import EXIT_INVALID, EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main
from tests.baseline_support import EXAMPLE_BASELINE, example_data

PATH = str(EXAMPLE_BASELINE)


def test_text_output_is_labelled_dry_run_and_not_ready(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["baseline-plan", PATH]) == EXIT_OK
    out = capsys.readouterr().out
    assert "BASELINE DRY RUN" in out
    assert "NOT EXECUTION READY" in out
    assert "NOT an authorisation" in out
    assert "disabled in this release" in out
    assert "-R0001" in out
    assert "SYN-101" not in out
    assert "softly lit" not in out
    assert "A/B/C/D" not in out


def test_json_output_distinguishes_plan_validity_from_readiness(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["baseline-plan", PATH, "--format", "json"]) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["plan_valid"] is True
    assert report["execution_ready"] is False
    assert report["counts"]["planned_runs"] == 4
    assert report["dry_run"] is True
    assert "live Wan 2.1 backend is disabled" in report["execution_blockers"]
    assert {r["clip_conditioning"] for r in report["runs"]} == {"original"}
    assert "frame_count" in report["unset_execution_fields"]


def test_pseudonyms_only_with_explicit_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["baseline-plan", PATH, "--show-pseudonyms", "--show-prompt-ids"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "SYN-101" in out
    assert "P01-neutral-motion" in out


def test_require_ready_exits_not_ready(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["baseline-plan", PATH, "--require-ready"]) == EXIT_NOT_READY


def test_no_execute_option_exists(capsys: pytest.CaptureFixture[str]) -> None:
    for flag in ("--execute", "--run", "--live", "--download", "--no-dry-run"):
        assert main(["baseline-plan", PATH, flag]) == EXIT_USAGE


@pytest.mark.parametrize(
    ("field", "value"),
    [("use_prompt_extend", True), ("clip_conditioning", "altered"), ("run_role", "bogus")],
)
def test_invalid_manifest_exits_1_without_echoing(
    field: str, value: Any, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    data = example_data()
    data[field] = value
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["baseline-plan", str(path)]) == EXIT_INVALID
    assert "bogus" not in capsys.readouterr().err


def test_ablation_manifest_is_rejected_by_the_baseline_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.conftest import EXAMPLE_MANIFEST

    assert main(["baseline-plan", str(EXAMPLE_MANIFEST)]) == EXIT_INVALID


def test_existing_commands_are_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    from tests.conftest import EXAMPLE_MANIFEST

    assert main(["plan", str(EXAMPLE_MANIFEST), "--dry-run"]) == EXIT_OK
    assert "A,B,C,D" in capsys.readouterr().out
    assert main(["plan", PATH, "--dry-run"]) == EXIT_INVALID  # baseline manifest is not ablation
