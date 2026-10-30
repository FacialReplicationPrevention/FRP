"""Provenance schema 1.0 and `frp provenance` tests.

Fixture records use fictitious SHAs and a fictitious organisation. The real Wan repository names
appear only where the protocol scope requires them; no weights, people or media are involved.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from typing import Any

import pytest
import yaml

from frp.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main
from frp.manifest import WAN21_I2V_CHECKPOINTS, WAN21_SOURCE_REPOSITORY
from frp.provenance import (
    MAX_PROVENANCE_BYTES,
    NOTICE,
    PROTOCOL_SCOPES,
    Permalink,
    ProvenanceError,
    load_provenance,
    parse_permalink,
    parse_provenance,
    parse_provenance_text,
    pending_claims,
)
from frp.results import PROTOCOL_MODEL_FAMILY, PROTOCOL_WAN21_I2V_CLIP_VAE_2X2
from tests.conftest import REPO_ROOT

INVENTORY = REPO_ROOT / "provenance" / "model-candidates.yaml"
PROTOCOL = PROTOCOL_WAN21_I2V_CLIP_VAE_2X2

SRC_21 = "1" * 40
REV_21 = "2" * 40
SRC_22 = "3" * 40
REV_22 = "4" * 40
GH_21 = f"https://github.com/Wan-Video/Wan2.1/blob/{SRC_21}"
GH_22 = f"https://github.com/Wan-Video/Wan2.2/blob/{SRC_22}"


def _claim(value: Any, status: str = "verified", evidence: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"value": value, "status": status, "evidence": list(evidence)}


def _wan21() -> dict[str, Any]:
    return {
        "candidate_id": "fixture-wan21-i2v",
        "model_family": "wan2.1-i2v",
        "task": "image-to-video",
        "provenance": "official",
        "frp_role": "initial-baseline",
        "source_repository": "Wan-Video/Wan2.1",
        "source_commit": _claim(
            SRC_21, evidence=(f"https://github.com/Wan-Video/Wan2.1/tree/{SRC_21}",)
        ),
        "checkpoint_repository": "Wan-AI/Wan2.1-I2V-14B-480P",
        "checkpoint_revision": _claim(
            REV_21, evidence=(f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/{REV_21}",)
        ),
        "weight_sha256": _claim(None, "not_verified"),
        "licence": _claim("Apache-2.0", evidence=(f"{GH_21}/LICENSE.txt",)),
        "conditioning": _claim(
            ["text_t5", "clip_vision", "vae_first_frame_concat"],
            evidence=(
                f"{GH_21}/wan/image2video.py#L1-L2",
                f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/{REV_21}/config.json",
            ),
        ),
        "derived_from": None,
        "protocols": [PROTOCOL],
        "execution_readiness": "not_ready",
    }


def _wan22() -> dict[str, Any]:
    return {
        "candidate_id": "fixture-wan22-i2v",
        "model_family": "wan2.2-i2v",
        "task": "image-to-video",
        "provenance": "official",
        "frp_role": "later-candidate",
        "source_repository": "Wan-Video/Wan2.2",
        "source_commit": _claim(
            SRC_22, evidence=(f"https://github.com/Wan-Video/Wan2.2/tree/{SRC_22}",)
        ),
        "checkpoint_repository": "Wan-AI/Wan2.2-I2V-A14B",
        "checkpoint_revision": _claim(
            REV_22, evidence=(f"https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/tree/{REV_22}",)
        ),
        "weight_sha256": _claim(None, "not_verified"),
        "licence": _claim("Apache-2.0", "pending"),
        "conditioning": _claim(
            ["text_t5", "vae_first_frame_concat"], evidence=(f"{GH_22}/wan/image2video.py#L3",)
        ),
        "derived_from": None,
        "protocols": [],
        "execution_readiness": "not_ready",
    }


def _derivative() -> dict[str, Any]:
    return {
        "candidate_id": "fixture-derivative",
        "model_family": "wan2.1-i2v",
        "task": "image-to-video",
        "provenance": "derivative",
        "frp_role": "inventory-only",
        "source_repository": None,
        "source_commit": _claim(None, "unknown"),
        "checkpoint_repository": "Fixture-Org/fixture-quantised-i2v",
        "checkpoint_revision": _claim(None, "not_verified"),
        "weight_sha256": _claim(None, "not_verified"),
        "licence": _claim("Apache-2.0", "pending"),
        "conditioning": _claim(None, "unknown"),
        "derived_from": _claim("Wan-AI/Wan2.1-I2V-14B-480P", "pending"),
        "protocols": [],
        "execution_readiness": "not_ready",
    }


@pytest.fixture
def inventory_data() -> dict[str, Any]:
    return {
        "provenance_schema_version": "1.0",
        "inventory_id": "FRP-TEST-INVENTORY",
        "reviewed_on": "2026-01-01",
        "candidates": [_wan21(), _wan22(), _derivative()],
    }


def _problems(data: Any) -> str:
    with pytest.raises(ProvenanceError) as info:
        parse_provenance(data)
    return "\n".join(info.value.problems)


def _run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- the committed inventory -------------------------------------------------------------------


def test_committed_inventory_is_valid_and_conservative():
    inventory = load_provenance(INVENTORY)
    by_id = {c.candidate_id: c for c in inventory.candidates}
    assert [c.candidate_id for c in inventory.candidates if c.frp_role == "initial-baseline"] == [
        "wan2.1-i2v-14b-480p"
    ]
    assert {c.candidate_id for c in inventory.candidates if c.protocols} == {"wan2.1-i2v-14b-480p"}
    assert all(c.weight_sha256.status == "not_verified" for c in inventory.candidates)
    assert all(c.execution_readiness == "not_ready" for c in inventory.candidates)
    assert "clip_vision" not in by_id["wan2.2-i2v-a14b"].conditioning.value
    assert by_id["wan2.2-i2v-a14b"].frp_role == "later-candidate"
    assert all(
        c.derived_from is not None for c in inventory.candidates if c.provenance != "official"
    )


def test_protocol_scope_matches_result_protocol_table():
    assert set(PROTOCOL_SCOPES) == set(PROTOCOL_MODEL_FAMILY)
    for protocol, scope in PROTOCOL_SCOPES.items():
        assert scope.model_family == PROTOCOL_MODEL_FAMILY[protocol]


def test_protocol_scope_matches_manifest_guard():
    scope = PROTOCOL_SCOPES[PROTOCOL]
    assert scope.source_repository == WAN21_SOURCE_REPOSITORY.casefold()
    assert scope.checkpoint_repositories == {c.casefold() for c in WAN21_I2V_CHECKPOINTS}


def test_synthetic_inventory_is_valid(inventory_data):
    inventory = parse_provenance(inventory_data)
    assert [c.candidate_id for c in inventory.candidates] == [
        "fixture-wan21-i2v",
        "fixture-wan22-i2v",
        "fixture-derivative",
    ]
    assert pending_claims(inventory.candidates[0]) == ["weight_sha256 (not_verified)"]
    assert "derived_from (pending)" in pending_claims(inventory.candidates[2])


# --- claim status rules ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        (_claim("Apache-2.0"), "a verified claim requires at least one evidence link"),
        (_claim(None), "status 'verified' requires a value"),
        (_claim(None, "pending"), "status 'pending' requires a value"),
        (_claim("Apache-2.0", "unknown"), "status 'unknown' requires value null"),
        (_claim("Apache-2.0", "not_verified"), "status 'not_verified' requires value null"),
        (
            _claim(
                "Apache-2.0",
                evidence=("https://github.com/Wan-Video/Wan2.1/blob/main/LICENSE.txt",),
            ),
            "verified evidence must be pinned to a 40-hex revision",
        ),
        (
            _claim("Apache-2.0", evidence=("https://arxiv.org/abs/2503.20314",)),
            "verified evidence must be pinned to a 40-hex revision",
        ),
        (
            _claim("Apache-2.0", "pending", (f"{GH_21}/LICENSE.txt", f"{GH_21}/LICENSE.txt")),
            "duplicate evidence link: [1] duplicates [0]",
        ),
        (_claim("Apache-2.0", "confirmed"), "Input should be 'verified', 'pending'"),
    ],
)
def test_claim_status_rules(inventory_data, claim, expected):
    inventory_data["candidates"][0]["licence"] = claim
    assert expected in _problems(inventory_data)


def test_versioned_arxiv_link_counts_as_pinned(inventory_data):
    inventory_data["candidates"][0]["licence"]["evidence"].append(
        "https://arxiv.org/abs/2503.20314v2"
    )
    parse_provenance(inventory_data)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/Wan-Video/Wan2.1",
        "file:///home/user/private/model",
        "/srv/private/checkpoints",
        "https://example.org/model",
        "https://github.com.evil.example/x",
    ],
)
def test_evidence_must_be_public_primary_source_https_url(inventory_data, url):
    inventory_data["candidates"][2]["licence"]["evidence"] = [url]
    problems = _problems(inventory_data)
    assert "candidates.2.licence.evidence.0: String should match pattern" in problems
    assert url not in problems


@pytest.mark.parametrize(
    "sha", ["main", "9737cba", "9737CBA9C1C3C4D04B33FCAD41C111989865D315", "g" * 40, "1" * 41]
)
def test_invalid_commit_sha_is_rejected(inventory_data, sha):
    inventory_data["candidates"][0]["source_commit"]["value"] = sha
    inventory_data["candidates"][1]["checkpoint_revision"]["value"] = sha
    problems = _problems(inventory_data)
    assert "candidates.0.source_commit.value: String should match pattern" in problems
    assert "candidates.1.checkpoint_revision.value: String should match pattern" in problems


def test_verified_commit_must_cite_its_own_pinned_link(inventory_data):
    inventory_data["candidates"][0]["source_commit"]["evidence"] = [
        f"https://github.com/Wan-Video/Wan2.2/tree/{SRC_21}"
    ]
    inventory_data["candidates"][1]["checkpoint_revision"]["evidence"] = [
        f"https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/tree/{REV_21}"
    ]
    problems = _problems(inventory_data)
    assert "source_commit: verified commit must cite a GitHub link to source_repository" in problems
    assert "checkpoint_revision: verified revision must cite a Hugging Face link" in problems


def test_commit_without_source_repository_is_rejected(inventory_data):
    inventory_data["candidates"][2]["source_commit"] = _claim(SRC_21, "pending")
    assert "source_commit: a commit requires source_repository" in _problems(inventory_data)


WRONG = "9" * 40


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/Wan-Video/Wan2.1/blob/{WRONG}/wan/image2video.py?rev={SRC_21}",
        f"https://github.com/Wan-Video/Wan2.1/tree/{WRONG}#{SRC_21}",
        f"https://github.com/Wan-Video/Wan2.1/blob/{WRONG}/{SRC_21}/README.md",
        f"https://github.com/Other-Org/Wan2.1/tree/{SRC_21}",
        f"https://github.com/Wan-Video/Wan2.1-fork/tree/{SRC_21}",
        f"https://huggingface.co/Wan-Video/Wan2.1/tree/{SRC_21}",
    ],
)
def test_verified_commit_requires_exact_revision_and_repository(inventory_data, url):
    inventory_data["candidates"][0]["source_commit"]["evidence"] = [url]
    problems = _problems(inventory_data)
    assert "source_commit: verified commit must cite a GitHub link to source_repository" in problems


@pytest.mark.parametrize(
    "url",
    [
        f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/{WRONG}?rev={REV_21}",
        f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/resolve/{WRONG}/x#{REV_21}",
        f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-720P/tree/{REV_21}",
        f"https://github.com/Wan-AI/Wan2.1-I2V-14B-480P/tree/{REV_21}",
    ],
)
def test_verified_revision_requires_exact_revision_and_repository(inventory_data, url):
    inventory_data["candidates"][0]["checkpoint_revision"]["evidence"] = [url]
    problems = _problems(inventory_data)
    assert "checkpoint_revision: verified revision must cite a Hugging Face link" in problems


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/Wan-Video/Wan2.1/blob/main/LICENSE.txt?x=/blob/{SRC_21}/",
        f"https://github.com/Wan-Video/Wan2.1/blob/main/LICENSE.txt#/tree/{SRC_21}",
        f"https://github.com/Wan-Video/Wan2.1/blob/{SRC_21}0/LICENSE.txt",
    ],
)
def test_revision_only_counts_as_pinned_in_the_url_path(inventory_data, url):
    inventory_data["candidates"][0]["licence"]["evidence"] = [url]
    assert "verified evidence must be pinned to a 40-hex revision" in _problems(inventory_data)


def test_repository_case_in_permalink_is_ignored(inventory_data):
    inventory_data["candidates"][0]["source_commit"]["evidence"] = [
        f"https://github.com/wan-video/WAN2.1/tree/{SRC_21}"
    ]
    parse_provenance(inventory_data)


def test_parse_permalink():
    assert parse_permalink(f"{GH_21}/wan/image2video.py?plain=1#L1-L2") == Permalink(
        host="github.com",
        repository="wan-video/wan2.1",
        kind="blob",
        revision=SRC_21,
        path="wan/image2video.py",
    )
    assert parse_permalink(f"https://huggingface.co/A/b/tree/{REV_21}") == Permalink(
        "huggingface.co", "a/b", "tree", REV_21, ""
    )
    for url in (
        f"https://github.com/A/b/blob/main/x?ref={SRC_21}",
        f"https://github.com/A/b/{SRC_21}",
        f"https://github.com/A/b/blob/{'AB' * 20}/x",
        f"https://arxiv.org/abs/{SRC_21}",
    ):
        assert parse_permalink(url) is None


def test_verified_conditioning_requires_evidence_at_pinned_commit(inventory_data):
    inventory_data["candidates"][1]["conditioning"]["evidence"] = [
        f"https://github.com/Wan-Video/Wan2.2/blob/{'5' * 40}/wan/image2video.py#L3"
    ]
    problems = _problems(inventory_data)
    assert "conditioning: verified evidence must be source files at the pinned" in problems


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/Wan-Video/Wan2.2/blob/{WRONG}/wan/image2video.py?rev={SRC_22}",
        f"https://github.com/Other-Org/Wan2.2/blob/{SRC_22}/wan/image2video.py",
        f"https://github.com/Wan-Video/Wan2.2/tree/{SRC_22}/wan",
        f"https://github.com/Wan-Video/Wan2.2/blob/{SRC_22}",
        f"https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/blob/{WRONG}/config.json?r={REV_22}",
        f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/{REV_22}/config.json",
    ],
)
def test_conditioning_evidence_requires_exact_pinned_file(inventory_data, url):
    inventory_data["candidates"][1]["conditioning"]["evidence"] = [url]
    problems = _problems(inventory_data)
    assert "conditioning: verified evidence must be source files at the pinned" in problems


def test_conditioning_evidence_may_cite_pinned_checkpoint_file(inventory_data):
    inventory_data["candidates"][1]["conditioning"]["evidence"].append(
        f"https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/resolve/{REV_22}/low_noise_model/config.json"
    )
    parse_provenance(inventory_data)


def test_verified_conditioning_requires_verified_source_commit(inventory_data):
    inventory_data["candidates"][1]["source_commit"] = _claim(SRC_22, "pending")
    assert "verified conditioning requires a verified source_commit" in _problems(inventory_data)


def test_duplicate_conditioning_paths_are_rejected(inventory_data):
    inventory_data["candidates"][1]["conditioning"]["value"].append("text_t5")
    assert "conditioning: duplicate path: [2] duplicates [0]" in _problems(inventory_data)


def test_unknown_conditioning_path_is_rejected(inventory_data):
    inventory_data["candidates"][1]["conditioning"]["value"].append("identity_channel")
    assert "candidates.1.conditioning.value.2: Input should be" in _problems(inventory_data)


# --- weight digests ----------------------------------------------------------------------------


def test_weight_digests_cannot_be_marked_verified(inventory_data):
    inventory_data["candidates"][0]["weight_sha256"] = _claim(
        {"shard-1.safetensors": "a" * 64},
        evidence=(f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/{REV_21}",),
    )
    assert "weight_sha256: cannot be verified in provenance schema 1.0" in _problems(inventory_data)


def test_platform_reported_weight_digests_may_be_pending(inventory_data):
    inventory_data["candidates"][0]["weight_sha256"] = _claim(
        {"transformer/shard-1.safetensors": "a" * 64}, "pending"
    )
    parse_provenance(inventory_data)


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"shard.bin": "abc"}, "String should match pattern"),
        ({"/home/LEAK-MARKER/shard.bin": "a" * 64}, "<key>.[key]: String should match pattern"),
        ({"../LEAK-MARKER.bin": "a" * 64}, "<key>.[key]: String should match pattern"),
        ({}, "Dictionary should have at least 1 item"),
    ],
)
def test_invalid_weight_digests_are_rejected_without_echo(inventory_data, files, expected):
    inventory_data["candidates"][0]["weight_sha256"] = _claim(files, "pending")
    problems = _problems(inventory_data)
    assert expected in problems
    assert "LEAK-MARKER" not in problems


# --- protocol declarations ---------------------------------------------------------------------


def test_wan21_protocol_cannot_be_applied_to_wan22(inventory_data):
    inventory_data["candidates"][1]["protocols"] = [PROTOCOL]
    problems = _problems(inventory_data)
    assert f"protocols.0: protocol {PROTOCOL} requires model_family wan2.1-i2v" in problems
    assert "does not apply to this source_repository" in problems
    assert "does not apply to this checkpoint_repository" in problems
    assert "requires conditioning path(s) absent from this candidate: clip_vision" in problems


def test_relabelling_wan22_as_wan21_family_is_still_rejected(inventory_data):
    candidate = inventory_data["candidates"][1]
    candidate["model_family"] = "wan2.1-i2v"
    candidate["protocols"] = [PROTOCOL]
    problems = _problems(inventory_data)
    assert "requires model_family" not in problems
    assert "does not apply to this source_repository" in problems
    assert "clip_vision" in problems


def test_protocol_requires_unmodified_official_checkpoint(inventory_data):
    inventory_data["candidates"][2]["protocols"] = [PROTOCOL]
    problems = _problems(inventory_data)
    assert "requires the unmodified official checkpoint" in problems
    assert "requires a verified source_commit" in problems
    assert "requires verified conditioning" in problems


def test_protocol_is_limited_to_the_reviewed_checkpoint(inventory_data):
    candidate = inventory_data["candidates"][0]
    candidate["checkpoint_repository"] = "Wan-AI/Wan2.1-I2V-14B-720P"
    candidate["checkpoint_revision"]["evidence"] = [
        f"https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-720P/tree/{REV_21}"
    ]
    candidate["conditioning"]["evidence"] = candidate["conditioning"]["evidence"][:1]
    assert "does not apply to this checkpoint_repository" in _problems(inventory_data)


def test_protocol_requires_verified_conditioning(inventory_data):
    inventory_data["candidates"][0]["conditioning"]["status"] = "pending"
    assert f"protocol {PROTOCOL} requires verified conditioning" in _problems(inventory_data)


def test_unsupported_protocol_is_rejected_without_echo(inventory_data):
    inventory_data["candidates"][1]["protocols"] = ["wan2.2-leak-marker-protocol"]
    problems = _problems(inventory_data)
    assert "protocols.0: unsupported protocol" in problems
    assert "leak-marker" not in problems


def test_duplicate_protocol_is_rejected(inventory_data):
    inventory_data["candidates"][0]["protocols"] = [PROTOCOL, PROTOCOL]
    assert "duplicate protocol: [1] duplicates [0]" in _problems(inventory_data)


# --- identities, duplicates and fixed fields ---------------------------------------------------


def test_duplicate_candidates_are_rejected(inventory_data):
    duplicate = copy.deepcopy(inventory_data["candidates"][2])
    duplicate["candidate_id"] = "FIXTURE-DERIVATIVE".lower()
    inventory_data["candidates"].append(duplicate)
    problems = _problems(inventory_data)
    assert "duplicate candidate_id: [3] duplicates [2]" in problems
    assert "duplicate checkpoint_repository: [3] duplicates [2]" in problems


def test_checkpoint_duplicates_are_case_insensitive(inventory_data):
    duplicate = copy.deepcopy(inventory_data["candidates"][2])
    duplicate["candidate_id"] = "fixture-derivative-2"
    duplicate["checkpoint_repository"] = "fixture-org/FIXTURE-QUANTISED-I2V"
    inventory_data["candidates"].append(duplicate)
    assert "duplicate checkpoint_repository: [3] duplicates [2]" in _problems(inventory_data)


def test_only_one_initial_baseline(inventory_data):
    inventory_data["candidates"][1]["frp_role"] = "initial-baseline"
    assert "at most one candidate may be the initial-baseline (candidates 0, 1)" in _problems(
        inventory_data
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("candidate_id", "Wan 2.1 I2V", "candidate_id: String should match pattern"),
        ("candidate_id", "unknown", "candidate_id: placeholder text is not allowed"),
        ("model_family", "TBD", "model_family: String should match pattern"),
        ("model_family", "todo", "model_family: placeholder text is not allowed"),
        ("checkpoint_repository", "Wan-AI", "checkpoint_repository: String should match pattern"),
        ("checkpoint_repository", "../etc/passwd", "String should match pattern"),
        ("source_repository", "Wan Video/Wan2.1", "source_repository: String should match"),
        ("task", "face-swap", "task: Input should be"),
        ("provenance", "community", "provenance: Input should be"),
        ("frp_role", "approved", "frp_role: Input should be"),
        ("execution_readiness", "ready", "execution_readiness: Input should be 'not_ready'"),
    ],
)
def test_invalid_identifiers_and_fixed_fields(inventory_data, field, value, expected):
    inventory_data["candidates"][2][field] = value
    assert expected in _problems(inventory_data)


def test_licence_placeholder_is_rejected(inventory_data):
    inventory_data["candidates"][2]["licence"]["value"] = "TBD"
    assert "licence.value: placeholder text is not allowed" in _problems(inventory_data)


def test_derived_from_matches_provenance(inventory_data):
    inventory_data["candidates"][0]["derived_from"] = _claim("Wan-AI/Other", "pending")
    inventory_data["candidates"][2]["derived_from"] = None
    problems = _problems(inventory_data)
    assert (
        "derived_from: required for, and only for, official-conversion and derivative" in problems
    )
    assert "candidates.0:" in problems
    assert "candidates.2:" in problems


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("provenance_schema_version", "2.0", "provenance_schema_version: Input should be '1.0'"),
        ("provenance_schema_version", 1.0, "provenance_schema_version: Input should be '1.0'"),
        ("inventory_id", "inventory one", "inventory_id: String should match pattern"),
        ("reviewed_on", "yesterday", "reviewed_on: Input should be a valid date"),
        ("candidates", [], "candidates: List should have at least 1 item"),
    ],
)
def test_invalid_top_level_fields(inventory_data, field, value, expected):
    inventory_data[field] = value
    assert expected in _problems(inventory_data)


def test_unknown_keys_are_rejected_without_echo(inventory_data):
    inventory_data["LEAK-MARKER-TOP"] = 1
    inventory_data["candidates"][0]["LEAK-MARKER-NESTED"] = 1
    inventory_data["candidates"][0]["licence"]["LEAK-MARKER-CLAIM"] = 1
    problems = _problems(inventory_data)
    assert "<key>: unknown key is not permitted by provenance schema 1.0" in problems
    assert "candidates.0.<key>: unknown key" in problems
    assert "candidates.0.licence.<key>: unknown key" in problems
    assert "LEAK-MARKER" not in problems


def test_errors_never_echo_input_values(inventory_data):
    marker = "LEAK-MARKER-VALUE"
    candidate = inventory_data["candidates"][2]
    candidate["candidate_id"] = marker
    candidate["checkpoint_repository"] = f"{marker}/{marker} x"
    candidate["licence"] = _claim({"text": marker}, "pending")
    candidate["derived_from"] = _claim([marker], "pending")
    candidate["conditioning"] = _claim([marker], "pending")
    assert marker not in _problems(inventory_data)


# --- loading -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("candidates: [\n", "malformed YAML at line"),
        ("a: 1\na: 2\n", "duplicate mapping key"),
        ("--- {}\n--- {}\n", "multiple documents"),
        ("!!python/object:os.system {}\n", "unsupported YAML construct"),
        ("- 1\n- 2\n", "top level must be a mapping"),
    ],
)
def test_malformed_yaml_is_rejected(text, expected):
    with pytest.raises(ProvenanceError) as info:
        parse_provenance_text(text)
    assert expected in "\n".join(info.value.problems)


def test_json_inventory_is_accepted(inventory_data):
    parse_provenance_text(json.dumps(inventory_data))


def test_unquoted_yaml_date_is_accepted(inventory_data):
    text = yaml.safe_dump(inventory_data, sort_keys=False).replace(
        "reviewed_on: '2026-01-01'", "reviewed_on: 2026-01-01"
    )
    assert "reviewed_on: 2026-01-01\n" in text
    assert parse_provenance_text(text).reviewed_on.isoformat() == "2026-01-01"


def test_missing_and_oversized_files(tmp_path):
    with pytest.raises(ProvenanceError, match="file not found"):
        load_provenance(tmp_path / "missing.yaml")
    big = tmp_path / "big.yaml"
    big.write_text("#" * (MAX_PROVENANCE_BYTES + 1), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="file exceeds"):
        load_provenance(big)


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_text_output_for_committed_inventory(capsys):
    code, out, err = _run(capsys, "provenance", str(INVENTORY))
    assert code == EXIT_OK
    assert err == ""
    assert out.startswith(NOTICE)
    assert "Execution readiness: NOT READY for every candidate" in out
    assert "wan2.1-i2v-14b-480p" in out
    assert PROTOCOL in out
    assert "weight_sha256 (not_verified)" in out
    assert str(INVENTORY.parent) not in out


def test_cli_json_output(capsys, inventory_data, write_manifest):
    path = write_manifest(inventory_data, "inventory.yaml")
    code, out, _ = _run(capsys, "provenance", str(path), "--format", "json")
    assert code == EXIT_OK
    report = json.loads(out)
    assert report["execution_ready_candidates"] == 0
    assert report["reviewed_on"] == "2026-01-01"
    first = report["candidates"][0]
    assert first["source_commit"] == {"value": SRC_21, "status": "verified", "evidence_links": 1}
    assert first["conditioning"]["value"] == ["text_t5", "clip_vision", "vae_first_frame_concat"]
    assert first["protocols"] == [PROTOCOL]
    assert first["execution_readiness"] == "not_ready"
    assert report["candidates"][2]["derived_from"]["status"] == "pending"


def test_cli_invalid_inventory_exits_1_without_echo(capsys, inventory_data, write_manifest):
    inventory_data["candidates"][1]["protocols"] = [PROTOCOL]
    inventory_data["candidates"][2]["candidate_id"] = "LEAK MARKER"
    path = write_manifest(inventory_data, "inventory.yaml")
    code, out, err = _run(capsys, "provenance", str(path))
    assert code == EXIT_INVALID
    assert out == ""
    assert "frp: invalid provenance inventory:" in err
    assert "clip_vision" in err
    assert "LEAK MARKER" not in err
    assert str(path.parent) not in err


@pytest.mark.parametrize("argv", [["provenance"], ["provenance", "x.yaml", "--format", "xml"]])
def test_cli_usage_errors(capsys, argv):
    code, _, _ = _run(capsys, *argv)
    assert code == EXIT_USAGE


def test_provenance_cli_runs_offline_without_heavy_imports():
    code = (
        "import sys, socket\n"
        "def _no_network(*a, **k): raise RuntimeError('network access attempted')\n"
        "socket.socket.connect = _no_network\n"
        "from frp.cli import main\n"
        f"assert main(['provenance', {str(INVENTORY)!r}]) == 0\n"
        "heavy = {'torch', 'numpy', 'cv2', 'PIL', 'transformers', 'diffusers', 'huggingface_hub'}\n"
        "print(sorted(heavy & set(sys.modules)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip().splitlines()[-1] == "[]"
