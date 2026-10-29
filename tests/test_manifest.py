from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from frp.manifest import (
    EXECUTION_FIELDS,
    SEED_MAX,
    ExperimentManifest,
    ManifestError,
    generation_controls_sha256,
    load_manifest,
    manifest_sha256,
    parse_manifest,
    parse_manifest_text,
    unset_execution_fields,
)
from tests.conftest import EXAMPLE_MANIFEST


def _problems(data: Any) -> str:
    with pytest.raises(ManifestError) as info:
        parse_manifest(data)
    return "\n".join(info.value.problems)


def test_example_manifest_is_valid_but_not_ready():
    manifest = load_manifest(EXAMPLE_MANIFEST)
    assert manifest.status == "planned"
    assert all(identity.pseudonym.startswith("SYN-") for identity in manifest.identities)
    assert "upstream_commit_sha" in unset_execution_fields(manifest)


def test_null_is_accepted_as_explicitly_unset(manifest_data):
    manifest = parse_manifest(manifest_data)
    assert set(unset_execution_fields(manifest)) == {
        *EXECUTION_FIELDS,
        "model_license_reviewed (must be true)",
    }


def test_fully_specified_manifest_is_ready(ready_manifest_data):
    assert unset_execution_fields(parse_manifest(ready_manifest_data)) == []


def test_execution_fields_are_exactly_the_nullable_schema_fields():
    nullable = {
        name
        for name, info in ExperimentManifest.model_fields.items()
        if type(None) in getattr(info.annotation, "__args__", ())
    }
    assert nullable == set(EXECUTION_FIELDS)


@pytest.mark.parametrize("field", ["experiment_id", "seeds", "identities", "sampler", "variants"])
def test_missing_required_field_is_rejected(manifest_data, field):
    del manifest_data[field]
    assert f"{field}: Field required" in _problems(manifest_data)


def test_unknown_field_is_rejected(manifest_data):
    manifest_data["reference_image_path"] = "/somewhere/photo.jpg"
    problems = _problems(manifest_data)
    assert "<key>: unknown key is not permitted by schema 1.0 (key name withheld)" in problems
    assert "reference_image_path" not in problems


@pytest.mark.parametrize(
    ("variants", "expected"),
    [
        (["A", "B", "C", "C", "D"], "duplicate variant(s): C"),
        (["A", "B", "C"], "missing variant(s): D"),
        ([], "missing variant(s): A, B, C, D"),
        (["A", "B", "C", "E"], "variants.3: Input should be 'A', 'B', 'C' or 'D'"),
        (["a", "B", "C", "D"], "variants.0: Input should be 'A', 'B', 'C' or 'D'"),
    ],
)
def test_invalid_variant_sets_are_rejected(manifest_data, variants, expected):
    manifest_data["variants"] = variants
    assert expected in _problems(manifest_data)


def test_variant_order_in_manifest_is_not_significant(manifest_data):
    manifest_data["variants"] = ["D", "C", "B", "A"]
    parse_manifest(manifest_data)


@pytest.mark.parametrize(
    ("seeds", "expected"),
    [
        ([], "seeds: List should have at least 1 item"),
        (None, "seeds: Input should be a valid list"),
        ([-1], "seeds.0: Input should be greater than or equal to 0"),
        ([SEED_MAX + 1], "seeds.0: Input should be less than or equal to"),
        ([True], "seeds.0: Input should be a valid integer"),
        ([1.0], "seeds.0: Input should be a valid integer"),
        (["42"], "seeds.0: Input should be a valid integer"),
        ([5, 6, 5], "duplicate seed(s): 5"),
        (42, "seeds: Input should be a valid list"),
    ],
)
def test_invalid_seed_assignments_are_rejected(manifest_data, seeds, expected):
    manifest_data["seeds"] = seeds
    assert expected in _problems(manifest_data)


def test_seed_bounds_are_inclusive(manifest_data):
    manifest_data["seeds"] = [0, SEED_MAX]
    assert parse_manifest(manifest_data).seeds == [0, SEED_MAX]


@pytest.mark.parametrize(
    "pseudonym", ["Jane Doe", "syn-001", "SYN001", "SYN-1", "jane.doe@example.org", ""]
)
def test_pseudonym_format_is_enforced(manifest_data, pseudonym):
    manifest_data["identities"] = [{"pseudonym": pseudonym}]
    assert "identities.0.pseudonym: String should match pattern" in _problems(manifest_data)


def test_identity_cannot_carry_extra_data(manifest_data):
    manifest_data["identities"][0]["embedding"] = [0.1, 0.2]
    assert "identities.0.<key>: unknown key is not permitted" in _problems(manifest_data)


def test_duplicate_pseudonyms_reported_by_position(manifest_data):
    manifest_data["identities"].append({"pseudonym": "SYN-001"})
    problems = _problems(manifest_data)
    assert "duplicate identity pseudonym: [2] duplicates [0]" in problems
    assert "SYN-001" not in problems


def test_duplicate_prompt_ids_and_texts_are_rejected(manifest_data):
    manifest_data["prompts"].append({"id": "P01", "text": "Synthetic test prompt two."})
    problems = _problems(manifest_data)
    assert "duplicate prompt id: [2] duplicates [0]" in problems
    assert "duplicate prompt text: [2] duplicates [1]" in problems


@pytest.mark.parametrize("value", ["TODO", "tbd", "<fill me in>", "{{ sha }}", "???", "N/A", " "])
def test_placeholder_text_is_rejected(manifest_data, value):
    manifest_data["sampler"] = value
    problems = _problems(manifest_data)
    assert problems.startswith("sampler: ")
    assert "placeholder" in problems or "at least 1 character" in problems


def test_placeholder_prompt_text_is_rejected(manifest_data):
    manifest_data["prompts"][0]["text"] = "TODO"
    assert "prompts.0.text: placeholder text is not allowed" in _problems(manifest_data)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", 1.0, "schema_version: Input should be '1.0'"),
        ("schema_version", "2.0", "schema_version: Input should be '1.0'"),
        ("status", "completed", "status: Input should be 'planned'"),
        ("consent_record_location", "repo/consent", "Input should be 'private_only'"),
        ("image_count_per_identity", 2, "image_count_per_identity: Input should be 1"),
        ("upstream_commit_sha", "main", "upstream_commit_sha: String should match pattern"),
        ("checkpoint_hashes", {"model.bin": "abc"}, "String should match pattern"),
        ("model_license_reviewed", "yes", "model_license_reviewed: Input should be a valid bool"),
        ("sampling_steps", 0, "sampling_steps: Input should be greater than or equal to 1"),
        ("guidance_scale", 0, "guidance_scale: Input should be greater than 0"),
        ("frame_count", 80, "frame_count: frame_count must have the form 4n+1"),
        ("resolution", "832x480", "resolution: String should match pattern"),
        ("frame_indices", [0, 40, 20], "frame_indices: frame_indices must be strictly increasing"),
        ("experiment_id", "exp 2", "experiment_id: String should match pattern"),
    ],
)
def test_invalid_field_values_have_clear_errors(manifest_data, field, value, expected):
    manifest_data[field] = value
    assert expected in _problems(manifest_data)


def test_number_of_identities_must_match_list(manifest_data):
    manifest_data["number_of_identities"] = 5
    assert "number_of_identities is 5 but 2 identities are listed" in _problems(manifest_data)


def test_frame_indices_must_fit_frame_count(ready_manifest_data):
    ready_manifest_data["frame_indices"] = [0, 81]
    assert "frame_indices must be < frame_count (81)" in _problems(ready_manifest_data)


def test_errors_never_echo_input_values(manifest_data):
    leak_marker = "PRIVATE-PROMPT-TEXT-SHOULD-NOT-LEAK"
    manifest_data["prompts"][0]["text"] = {"nested": leak_marker}
    manifest_data["sampler"] = ["not", "a", "string", leak_marker]
    manifest_data["unexpected"] = leak_marker
    assert leak_marker not in _problems(manifest_data)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("seeds: [1, 2\n", "malformed YAML at line"),
        ("- just\n- a list\n", "top level must be a mapping"),
        ("", "top level must be a mapping"),
        ("experiment_id: A\nexperiment_id: B\n", "at line 2, column 1: duplicate mapping key"),
        ("seeds: !custom_tag 1\n", "unsupported YAML construct"),
        ("a: 1\n---\nb: 2\n", "invalid YAML document"),
        ("? [a, b]\n: 1\n", "mapping keys must be scalars"),
    ],
)
def test_malformed_yaml_is_rejected(text, expected):
    with pytest.raises(ManifestError) as info:
        parse_manifest_text(text)
    assert expected in "\n".join(info.value.problems)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ManifestError, match="file not found"):
        load_manifest(tmp_path / "absent.yaml")


def test_hashes_ignore_formatting_but_track_content(manifest_data, write_manifest):
    compact = load_manifest(write_manifest(manifest_data, "a.yaml"))
    commented = load_manifest(
        write_manifest("# comment\n" + EXAMPLE_MANIFEST.read_text().replace("FRP-EXP", "FRP-X"))
    )
    again = parse_manifest(manifest_data)
    assert manifest_sha256(compact) == manifest_sha256(again)
    assert manifest_sha256(compact) != manifest_sha256(commented)

    manifest_data["seeds"] = [99]
    changed_seed = parse_manifest(manifest_data)
    assert generation_controls_sha256(changed_seed) == generation_controls_sha256(compact)
    manifest_data["sampler"] = "other-sampler"
    assert generation_controls_sha256(parse_manifest(manifest_data)) != (
        generation_controls_sha256(compact)
    )


def test_errors_never_echo_user_supplied_keys(manifest_data):
    marker = "Private Name Marker"
    manifest_data[marker] = 1
    manifest_data["identities"] = [{marker: "x"}]
    manifest_data["alteration_parameters"] = {marker: [1]}
    manifest_data["checkpoint_hashes"] = {marker: "not-a-hash"}
    problems = _problems(manifest_data)
    assert marker not in problems
    assert "alteration_parameters.<key>.bool: Input should be a valid boolean" in problems
    assert "checkpoint_hashes.<key>: String should match pattern" in problems


@pytest.mark.parametrize(
    "text",
    [
        "Private Name Marker: 1\nPrivate Name Marker: 2\n",
        "seeds: !Private_Name_Marker 1\n",
        'prompts: [{id: P1, text: "Private Name Marker \\q"}]\n',
    ],
)
def test_yaml_errors_never_echo_input(text):
    with pytest.raises(ManifestError) as info:
        parse_manifest_text(text)
    assert "Private" not in str(info.value)
    assert "Marker" not in str(info.value)


def test_deeply_nested_yaml_is_a_clean_validation_failure():
    with pytest.raises(ManifestError, match="nest"):
        parse_manifest_text("seeds: " + "[" * 5000 + "]" * 5000 + "\n")


def test_json_manifest_with_exponent_floats_keeps_numeric_types(manifest_data):
    manifest_data["alteration_parameters"] = {"sigma": 0.00001, "scale": 1e16}
    manifest_data["guidance_scale"] = 5e0
    manifest = parse_manifest_text(json.dumps(manifest_data))
    assert manifest.alteration_parameters == {"sigma": 1e-05, "scale": 1e16}
    assert manifest.guidance_scale == 5.0
    assert manifest_sha256(manifest) == manifest_sha256(parse_manifest(manifest_data))


@pytest.mark.parametrize("value", [".inf", ".nan", "-.inf"])
def test_non_finite_floats_are_rejected(manifest_data, value):
    text = yaml.safe_dump(manifest_data, sort_keys=False)
    text = text.replace("guidance_scale: null", f"guidance_scale: {value}")
    with pytest.raises(ManifestError, match="guidance_scale: Input should be a finite number"):
        parse_manifest_text(text)
    text = yaml.safe_dump(manifest_data, sort_keys=False).replace(
        "alteration_parameters: null", f"alteration_parameters: {{k: {value}}}"
    )
    with pytest.raises(ManifestError, match="finite number"):
        parse_manifest_text(text)
