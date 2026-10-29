"""Aggregate-only Markdown/CSV reports: simulated marking, missing values and redaction."""

from __future__ import annotations

import copy
import csv
import io
from dataclasses import replace

import pytest

from frp.aggregation import aggregate
from frp.cli import EXIT_OK, main
from frp.manifest import load_manifest, parse_manifest
from frp.reporting import (
    CSV_COLUMNS,
    SIMULATED_BANNER,
    ReportError,
    render_csv,
    render_markdown,
    write_reports,
)
from frp.simulation import SCENARIOS, simulate_experiment
from tests.conftest import EXAMPLE_MANIFEST, load_results, results_dict, set_frames


@pytest.fixture
def summary():
    return aggregate(simulate_experiment(load_manifest(EXAMPLE_MANIFEST), "mixed"))


def _csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_banner_is_exact_and_prominent(summary):
    assert SIMULATED_BANNER == "SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE"
    markdown = render_markdown(summary)
    lines = markdown.splitlines()
    assert lines[0] == "# FRP simulated pipeline report"
    assert lines[2] == f"> **{SIMULATED_BANNER}**"
    assert "do **not** show that any conditioning alteration reduces identity" in markdown


def test_every_csv_row_carries_the_simulated_marker(summary):
    text = render_csv(summary)
    assert text.splitlines()[0] == ",".join(CSV_COLUMNS)
    rows = _csv(text)
    assert rows
    assert {row["data_provenance"] for row in rows} == {SIMULATED_BANNER}
    assert {row["report_schema_version"] for row in rows} == {"1.0"}
    assert {row["value_status"] for row in rows} <= {"available", "not_available", "not_computed"}
    for row in rows:
        assert (row["value"] == "") == (row["value_status"] != "available")


def test_csv_contains_expected_sections(summary):
    rows = _csv(render_csv(summary))
    sections = {row["section"] for row in rows}
    assert sections == {
        "provenance",
        "conditioning",
        "execution",
        "face_detection",
        "similarity",
        "quality",
        "paired_comparison",
    }
    subjects = {row["subject"] for row in rows if row["section"] == "paired_comparison"}
    assert subjects == {"B-A", "C-A", "D-A"}
    intervals = [row for row in rows if row["metric"].endswith(".interval")]
    assert len(intervals) == 6
    assert {row["value_status"] for row in intervals} == {"not_computed"}


def test_reports_are_deterministic(summary):
    again = aggregate(simulate_experiment(load_manifest(EXAMPLE_MANIFEST), "mixed"))
    assert render_markdown(summary) == render_markdown(again)
    assert render_csv(summary) == render_csv(again)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_scenario_renders(scenario):
    summary = aggregate(simulate_experiment(load_manifest(EXAMPLE_MANIFEST), scenario))
    assert SIMULATED_BANNER in render_markdown(summary)
    assert _csv(render_csv(summary))


def test_missing_values_are_explicit(small_manifest_data):
    data = results_dict(small_manifest_data)
    for run in data["runs"]:
        if run["variant"] == "D":
            set_frames(run, "absent", "absent", "absent")
    summary = aggregate(load_results(data))
    rows = _csv(render_csv(summary))
    d_similarity = next(
        r for r in rows if r["subject"] == "D" and r["metric"] == "median_later_frame_similarity"
    )
    assert (d_similarity["value"], d_similarity["value_status"]) == ("", "not_available")
    markdown = render_markdown(summary)
    assert "| D | n/a | 0 / 3 |" in markdown
    assert "insufficient: no identity has a complete pair" in markdown


def test_non_simulated_results_cannot_be_reported(small_manifest_data):
    data = results_dict(small_manifest_data)
    data["simulated"] = False
    data["simulation_scenario"] = None
    for component in ("executor", "face_evaluator", "quality_evaluator"):
        data[component]["simulated"] = False
    summary = aggregate(load_results(data))
    with pytest.raises(ReportError, match="privacy review"):
        render_markdown(summary)
    with pytest.raises(ReportError):
        render_csv(summary)


@pytest.mark.parametrize("component", ["executor", "face_evaluator", "quality_evaluator"])
def test_reports_require_every_component_simulated(summary, component):
    real = getattr(summary, component).model_copy(update={"simulated": False})
    tampered = replace(summary, **{component: real})
    assert tampered.simulated is True
    with pytest.raises(ReportError, match="fully simulated"):
        render_markdown(tampered)
    with pytest.raises(ReportError, match="fully simulated"):
        render_csv(tampered)


def test_write_reports_refuses_to_overwrite(summary, tmp_path):
    md, table = write_reports(summary, tmp_path / "out")
    assert md.read_text(encoding="utf-8") == render_markdown(summary)
    assert table.read_text(encoding="utf-8") == render_csv(summary)
    with pytest.raises(FileExistsError):
        write_reports(summary, tmp_path / "out")
    write_reports(summary, tmp_path / "out", overwrite=True)


# --- Adversarial redaction --------------------------------------------------------------------

PSEUDONYM_MARKER = "LEAKME-424242"
PROMPT_ID_MARKER = "Private-Prompt-Id-Marker"
PROMPT_TEXT_MARKER = "PRIVATE-PROMPT-TEXT /home/participant/portrait.jpg"
SEED_MARKER = 987654321


@pytest.fixture
def adversarial_manifest(manifest_data):
    data = copy.deepcopy(manifest_data)
    data["identities"][0]["pseudonym"] = PSEUDONYM_MARKER
    data["prompts"][0]["id"] = PROMPT_ID_MARKER
    data["prompts"][0]["text"] = PROMPT_TEXT_MARKER
    data["seeds"][0] = SEED_MARKER
    return data


def _assert_no_private_strings(text: str, results) -> None:
    for marker in (
        PSEUDONYM_MARKER,
        "LEAKME",
        PROMPT_ID_MARKER,
        "PRIVATE-PROMPT-TEXT",
        "/home/participant",
        "portrait.jpg",
        str(SEED_MARKER),
        "SYN-00",
        "simulated://",
        "identity-0",
    ):
        assert marker not in text, marker
    for run in results.runs:
        assert run.run_id not in text
        if run.execution.artefact is not None:
            assert run.execution.artefact.uri not in text


def test_reports_contain_no_participant_like_or_path_data(adversarial_manifest):
    results = simulate_experiment(parse_manifest(adversarial_manifest), "mixed")
    summary = aggregate(results)
    for text in (render_markdown(summary), render_csv(summary)):
        _assert_no_private_strings(text, results)


def test_cli_outputs_contain_no_private_data(
    adversarial_manifest, write_manifest, tmp_path, capsys
):
    report_dir = tmp_path / "PRIVATE-DIR-MARKER"
    path = write_manifest(adversarial_manifest)
    code = main(["simulate", str(path), "--report-dir", str(report_dir)])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    results = simulate_experiment(parse_manifest(adversarial_manifest), "mixed")
    texts = [
        captured.out,
        captured.err,
        (report_dir / "report.md").read_text(encoding="utf-8"),
        (report_dir / "summary.csv").read_text(encoding="utf-8"),
    ]
    for text in texts:
        _assert_no_private_strings(text, results)
        assert "PRIVATE-DIR-MARKER" not in text
        assert str(tmp_path) not in text
