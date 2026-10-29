"""Result schema 1.0: null rules, strictness, group integrity and plan linkage."""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from frp.manifest import parse_manifest
from frp.planner import generate_run_plan
from frp.results import (
    ExecutionRecord,
    FrameEvaluation,
    QualityEvaluation,
    ResultValidationError,
    parse_result_set_json,
    verify_results_against_plan,
)
from tests.conftest import fail_run, find_run, load_results, results_dict, set_frames

# --- Frame / quality / execution null rules -------------------------------------------------


@pytest.mark.parametrize("status", ["absent", "multiple", "low_quality", "error", "not_evaluated"])
def test_similarity_must_be_null_unless_face_is_valid(status):
    assert FrameEvaluation(frame_index=0, face_status=status, similarity=None).similarity is None
    for placeholder in (0.0, 0, -1.0):
        with pytest.raises(ValidationError, match="null for every other status"):
            FrameEvaluation(frame_index=0, face_status=status, similarity=placeholder)


def test_valid_face_requires_similarity():
    with pytest.raises(ValidationError, match="must be a number for a valid face"):
        FrameEvaluation(frame_index=0, face_status="valid", similarity=None)
    assert FrameEvaluation(frame_index=0, face_status="valid", similarity=0.5).similarity == 0.5


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.01, 1.01, True, "0.5"])
def test_invalid_similarity_values_are_rejected(bad):
    with pytest.raises(ValidationError):
        FrameEvaluation(frame_index=0, face_status="valid", similarity=bad)


@pytest.mark.parametrize("bad_index", [-1, 1.0, "0"])
def test_invalid_frame_index_rejected(bad_index):
    with pytest.raises(ValidationError):
        FrameEvaluation(frame_index=bad_index, face_status="absent", similarity=None)


def test_quality_score_only_when_scored():
    with pytest.raises(ValidationError):
        QualityEvaluation(status="scored", score=None)
    for status in ("unscorable", "error", "not_evaluated"):
        with pytest.raises(ValidationError):
            QualityEvaluation(status=status, score=0.0)
    with pytest.raises(ValidationError):
        QualityEvaluation(status="scored", score=float("nan"))


def test_execution_record_rules():
    artefact = {"uri": "simulated://artefact/abc"}
    with pytest.raises(ValidationError):
        ExecutionRecord(status="succeeded", artefact=None, failure_category=None, gpu_seconds=None)
    with pytest.raises(ValidationError):
        ExecutionRecord(status="failed", artefact=None, failure_category=None, gpu_seconds=None)
    with pytest.raises(ValidationError):
        ExecutionRecord(
            status="failed", artefact=artefact, failure_category="other", gpu_seconds=None
        )
    with pytest.raises(ValidationError):
        ExecutionRecord(
            status="not_executed", artefact=None, failure_category=None, gpu_seconds=1.0
        )
    with pytest.raises(ValidationError):
        ExecutionRecord(
            status="succeeded", artefact=artefact, failure_category=None, gpu_seconds=-1.0
        )


def test_artefact_uri_must_be_a_uri():
    with pytest.raises(ValidationError):
        ExecutionRecord(
            status="succeeded",
            artefact={"uri": "/home/someone/private/video.mp4"},
            failure_category=None,
            gpu_seconds=None,
        )


# --- RunResult / ResultSet ------------------------------------------------------------------


@pytest.fixture
def data(small_manifest_data):
    return results_dict(small_manifest_data)


def _problems(data) -> str:
    with pytest.raises(ResultValidationError) as excinfo:
        load_results(data)
    return "\n".join(excinfo.value.problems)


def test_simulated_result_set_round_trips_through_json(data):
    results = load_results(data)
    again = parse_result_set_json(results.model_dump_json())
    assert again == results
    assert results.result_schema_version == "1.0"
    assert results.protocol == "wan2.1-i2v-clip-vae-2x2"


def test_failed_run_cannot_carry_evaluations(data):
    run = find_run(data, 1, "B")
    fail_run(run)
    load_results(data)
    run["frames"][1] = {"frame_index": 10, "face_status": "valid", "similarity": 0.5}
    assert "must have face and quality status not_evaluated" in _problems(data)


def test_failed_run_cannot_carry_quality(data):
    run = find_run(data, 1, "B")
    fail_run(run)
    run["quality"] = {"status": "error", "score": None}
    assert "must have face and quality status not_evaluated" in _problems(data)


def test_conditioning_must_match_variant(data):
    find_run(data, 1, "B")["clip_conditioning"] = "original"
    assert "conditioning does not match the protocol for variant B" in _problems(data)


def test_run_id_must_match_group_and_variant(data):
    a, b = find_run(data, 1, "A"), find_run(data, 1, "B")
    a["run_id"], b["run_id"] = b["run_id"], a["run_id"]
    assert "run_id does not match group_index and variant" in _problems(data)


def test_duplicate_records_rejected(data):
    data["runs"].append(copy.deepcopy(data["runs"][0]))
    problems = _problems(data)
    assert "duplicate result record(s)" in problems
    assert "group 1: must have exactly one record per variant" in problems


def test_group_missing_a_variant_rejected(data):
    data["runs"] = [r for r in data["runs"] if (r["group_index"], r["variant"]) != (2, "C")]
    assert "group 2: must have exactly one record per variant" in _problems(data)


def test_group_members_must_share_identity_prompt_seed(data):
    find_run(data, 1, "D")["seed"] = 99
    assert "group 1: identity, prompt or seed differ in group" in _problems(data)


def test_frame_indices_must_match_declaration(data):
    set_frames(find_run(data, 1, "A"), 0.5, 0.5, 0.5)
    find_run(data, 1, "A")["frames"][2]["frame_index"] = 30
    assert "frame indices differ from the declared frame_indices" in _problems(data)


def test_quality_score_must_be_within_declared_scale(data):
    find_run(data, 1, "A")["quality"] = {"status": "scored", "score": 6.0}
    assert "quality score is outside the declared rubric scale" in _problems(data)


def test_simulated_flags_must_be_consistent(data):
    data["simulated"] = False
    data["simulation_scenario"] = None
    problems = _problems(data)
    assert "results from any simulated component must be marked simulated" in problems
    assert "simulation_default" not in problems


def test_scenario_requires_simulated(data):
    data["simulation_scenario"] = None
    assert "simulation_scenario is required for, and only for" in _problems(data)


def test_protocol_is_tied_to_wan21_model_family(data):
    data["executor"]["model_family"] = "wan2.2-i2v"
    assert "executor model_family must be wan2.1-i2v" in _problems(data)
    data["executor"]["model_family"] = "wan2.1-i2v"
    data["protocol"] = "wan2.2-i2v-something"
    assert "protocol" in _problems(data)


def test_component_names_cannot_be_paths(data):
    data["executor"]["revision"] = "/home/user/private"
    assert "executor.revision" in _problems(data)


def test_unknown_keys_rejected_without_echoing_names_or_values(data):
    data["runs"][0]["LEAK-KEY-MARKER"] = "LEAK-VALUE-MARKER"
    find_run(data, 1, "B")["frames"][0]["similarity"] = "LEAK-VALUE-MARKER-2"
    problems = _problems(data)
    assert "unknown key is not permitted" in problems
    assert "LEAK" not in problems


def test_type_coercion_rejected(data):
    find_run(data, 1, "A")["seed"] = "1"
    assert "seed" in _problems(data)


def test_oversized_input_rejected():
    with pytest.raises(ResultValidationError, match="exceeds"):
        parse_result_set_json(" " * (16_777_216 + 1))


def test_malformed_json_is_reported_safely():
    with pytest.raises(ResultValidationError) as excinfo:
        parse_result_set_json('{"runs": [ "SECRET-PATH /home/x" ')
    assert "SECRET" not in "\n".join(excinfo.value.problems)


# --- Plan linkage ---------------------------------------------------------------------------


def test_results_match_their_plan(small_manifest_data):
    manifest = parse_manifest(small_manifest_data)
    verify_results_against_plan(
        load_results(results_dict(small_manifest_data)), generate_run_plan(manifest), manifest
    )


def test_missing_and_orphaned_records_rejected(small_manifest_data):
    results = load_results(results_dict(small_manifest_data))
    fewer = copy.deepcopy(small_manifest_data) | {"seeds": [1]}
    more = copy.deepcopy(small_manifest_data) | {"seeds": [1, 2, 3]}
    for other, expected in ((fewer, "orphaned"), (more, "has no result record")):
        manifest = parse_manifest(other)
        with pytest.raises(ResultValidationError) as excinfo:
            verify_results_against_plan(results, generate_run_plan(manifest), manifest)
        assert expected in "\n".join(excinfo.value.problems)
        assert "manifest_sha256 does not match the plan" in excinfo.value.problems


def test_record_contents_must_match_planned_run(small_manifest_data):
    data = results_dict(small_manifest_data)
    for variant in "ABCD":
        find_run(data, 1, variant)["seed"] = 2
    manifest = parse_manifest(small_manifest_data)
    with pytest.raises(ResultValidationError) as excinfo:
        verify_results_against_plan(load_results(data), generate_run_plan(manifest), manifest)
    assert sum("does not match its planned run" in p for p in excinfo.value.problems) == 4


def test_duplicate_records_rejected_by_plan_check_even_if_schema_bypassed(small_manifest_data):
    results = load_results(results_dict(small_manifest_data))
    bypassed = results.model_construct(
        **(dict(results) | {"runs": (*results.runs, results.runs[0])})
    )
    manifest = parse_manifest(small_manifest_data)
    with pytest.raises(ResultValidationError, match="has 2 result records"):
        verify_results_against_plan(bypassed, generate_run_plan(manifest))


def _as_real(data):
    data = copy.deepcopy(data)
    data["simulated"] = False
    data["simulation_scenario"] = None
    for component in ("executor", "face_evaluator", "quality_evaluator"):
        data[component]["simulated"] = False
    return data


def test_non_simulated_results_require_manifest_declarations(small_manifest_data):
    manifest_data = copy.deepcopy(small_manifest_data) | {"frame_indices": None}
    data = _as_real(results_dict(manifest_data))
    assert "only allowed for simulated results" in _problems(copy.deepcopy(data))
    data["frame_indices_source"] = "manifest"
    results = load_results(data)
    manifest = parse_manifest(manifest_data)
    with pytest.raises(ResultValidationError) as excinfo:
        verify_results_against_plan(results, generate_run_plan(manifest), manifest)
    problems = excinfo.value.problems
    assert "non-simulated results require frame_indices declared in the manifest" in problems
    assert "face evaluator revision differs from the manifest" in problems
    assert "quality evaluator revision differs from quality_rubric_version" in problems


def test_manifest_frame_indices_must_match(small_manifest_data):
    data = results_dict(small_manifest_data)
    other = copy.deepcopy(small_manifest_data) | {"frame_indices": [0, 10, 30]}
    data_json = json.dumps(data)
    manifest = parse_manifest(other)
    plan = generate_run_plan(parse_manifest(small_manifest_data))
    with pytest.raises(ResultValidationError, match="frame_indices differ from the manifest"):
        verify_results_against_plan(parse_result_set_json(data_json), plan, manifest)
