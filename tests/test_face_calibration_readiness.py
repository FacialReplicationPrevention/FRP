"""PR 3I: synthetic adverse-case regression tests for face-evaluation/calibration readiness.

SIMULATED / METHOD TEST ONLY. Every number below is a fabricated, illustrative value with no
inferential meaning: no image, embedding, weight or real person is involved, and nothing here
estimates a real recogniser's performance, a threshold or a population.

The FMR/FNMR helper below is deliberately *test-local*: a production calibration API was
rejected (docs/face-evaluation-readiness.md, section 7). Existing contracts are reused.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from frp.baseline.aggregation import aggregate_baseline, summarise_attempt
from frp.baseline.analysis_plan import parse_analysis_plan
from frp.manifest import ManifestError
from frp.provenance import load_provenance
from frp.readiness import GATE_IDS, load_readiness
from tests.test_analysis_plan import _data
from tests.test_baseline_evaluation import FixedQuality, PatternFace, evaluate, plan, unevaluated

__all__ = ["plan", "unevaluated"]  # pytest fixtures re-exported for this module

ROOT = Path(__file__).resolve().parents[1]


# Test-local synthetic score fixtures -----------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    person_a: str
    person_b: str
    label: str  # "genuine" or "impostor"
    score: float | None  # None: no valid face, so no score
    source: str = "photo"  # "photo" or "video"


def _validate(pairs: Sequence[Pair]) -> None:
    for pair in pairs:
        if pair.label not in {"genuine", "impostor"}:
            raise ValueError("invalid label")
        if (pair.label == "genuine") != (pair.person_a == pair.person_b):
            raise ValueError("label contradicts fake identities")
        if pair.score is not None and not (math.isfinite(pair.score) and -1 <= pair.score <= 1):
            raise ValueError("score must be finite and within [-1, 1]")


def _check_split(calibration: set[str], evaluation: set[str]) -> None:
    if calibration & evaluation:
        raise ValueError("calibration and evaluation people overlap")
    if len(calibration) < 2:
        raise ValueError("at least two calibration people needed")


def rates(pairs: Sequence[Pair], threshold: float) -> dict[str, float | int | None]:
    """Counts and rates at a caller-supplied threshold; match means ``score >= threshold``."""
    _validate(pairs)
    out: dict[str, float | int | None] = {}
    counts: dict[str, tuple[int, int]] = {}
    for label in ("genuine", "impostor"):
        scored = [p.score for p in pairs if p.label == label and p.score is not None]
        matches = sum(1 for s in scored if s >= threshold)
        counts[label] = (matches, len(scored))
        out[f"{label}_excluded"] = sum(1 for p in pairs if p.label == label and p.score is None)
        out[f"{label}_scored"] = len(scored)
        out[f"{label}_matches"] = matches
    (gm, gn), (im, inn) = counts["genuine"], counts["impostor"]
    out["fnmr"] = (gn - gm) / gn if gn else None  # undefined, never 0, without genuine pairs
    out["fmr"] = im / inn if inn else None
    return out


# Rates, boundaries and undefined cases (synthetic) ---------------------------------------------


def test_rates_use_supplied_threshold_with_inclusive_boundary() -> None:
    pairs = [
        Pair("A", "A", "genuine", 0.8),
        Pair("B", "B", "genuine", 0.5),
        Pair("A", "B", "impostor", 0.5),
        Pair("A", "C", "impostor", 0.1),
    ]
    r = rates(pairs, 0.5)
    assert (r["genuine_matches"], r["impostor_matches"]) == (2, 1)  # >= counts ties as matches
    assert (r["fnmr"], r["fmr"]) == (0.0, 0.5)
    r = rates(pairs, 0.6)
    assert (r["fnmr"], r["fmr"]) == (0.5, 0.0)  # FMR and FNMR trade off as the threshold moves


def test_zero_denominators_are_undefined_not_zero() -> None:
    only_genuine = [Pair("A", "A", "genuine", 0.9)]
    assert rates(only_genuine, 0.5)["fmr"] is None
    only_impostor = [Pair("A", "B", "impostor", 0.9)]
    assert rates(only_impostor, 0.5)["fnmr"] is None
    assert rates([], 0.5)["fmr"] is None


def test_unscored_pairs_are_counted_as_excluded_and_never_as_zero_scores() -> None:
    pairs = [
        Pair("A", "A", "genuine", 0.9),
        Pair("A", "A", "genuine", None),
        Pair("A", "B", "impostor", None),
    ]
    r = rates(pairs, 0.5)
    assert (r["genuine_scored"], r["genuine_excluded"]) == (1, 1)
    assert (r["impostor_scored"], r["impostor_excluded"]) == (0, 1)
    assert r["fmr"] is None
    assert r["fnmr"] == 0.0


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf, 1.5, -1.01])
def test_nonfinite_and_out_of_range_scores_are_rejected(score: float) -> None:
    with pytest.raises(ValueError, match="score"):
        rates([Pair("A", "A", "genuine", score)], 0.5)


def test_labels_must_agree_with_fake_identities() -> None:
    with pytest.raises(ValueError, match="contradicts"):
        rates([Pair("A", "B", "genuine", 0.5)], 0.5)
    with pytest.raises(ValueError, match="contradicts"):
        rates([Pair("A", "A", "impostor", 0.5)], 0.5)
    with pytest.raises(ValueError, match="invalid label"):
        rates([Pair("A", "A", "maybe", 0.5)], 0.5)


def test_split_leakage_and_too_few_people_are_rejected() -> None:
    with pytest.raises(ValueError, match="overlap"):
        _check_split({"P1", "P2"}, {"P2", "P3"})
    with pytest.raises(ValueError, match="at least two"):
        _check_split({"P1"}, {"P3"})
    _check_split({"P1", "P2"}, {"P3"})  # a synthetic disjoint split is accepted


def test_one_threshold_need_not_transfer_between_photo_and_video_controls() -> None:
    # Illustrative synthetic shift: generated-video impostor scores sit higher than photo ones.
    photo = [Pair("A", "B", "impostor", s) for s in (0.05, 0.10, 0.15, 0.20)]
    video = [Pair("A", "B", "impostor", s, "video") for s in (0.20, 0.30, 0.40, 0.50)]
    assert rates(photo, 0.25)["fmr"] == 0.0
    assert rates(video, 0.25)["fmr"] == 0.75  # same threshold, different error: no transfer


# Existing contracts under adverse synthetic conditions -----------------------------------------


def test_every_non_valid_status_has_no_similarity_and_no_fake_zero(plan, unevaluated) -> None:
    for status in ("absent", "multiple", "low_quality", "error"):
        face = PatternFace(("valid", status, status, status, status), (0.9, None, None, None, None))
        evaluated = evaluate(plan, unevaluated, face, FixedQuality())
        clip = summarise_attempt(evaluated.attempts[0], min_valid_later_frames=1)
        assert clip.later_frame_similarity is None  # missing, not 0.0
        assert clip.later_similarity_status == "insufficient_valid_later_frames"
        assert clip.later_face_status_counts[status] == 4
        assert clip.first_frame_similarity == 0.9


def test_detector_coverage_failure_keeps_denominators_and_yields_no_summary_similarity(
    plan, unevaluated
) -> None:
    face = PatternFace(("absent",) * 5, (None,) * 5)
    evaluated = evaluate(plan, unevaluated, face, FixedQuality())
    summary = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
    )
    assert summary.calibration_status == "uncalibrated"
    assert summary.face_status_counts["absent"] == 5 * 3  # three succeeded clips, all frames
    assert sum(summary.face_status_counts.values()) == summary.frames_declared
    assert all(a.later_frame_similarity is None for a in summary.attempts)


def test_aggregation_never_derives_or_accepts_a_threshold(plan, unevaluated) -> None:
    evaluated = evaluate(plan, unevaluated, PatternFace(("valid",) * 5, (0.9,) * 5), FixedQuality())
    with pytest.raises(TypeError):
        aggregate_baseline(  # type: ignore[call-arg]
            evaluated,
            plan,
            min_valid_later_frames=1,
            attempt_selection="first_attempt",
            threshold=0.5,
        )
    summary = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
    )
    assert summary.calibration_status == "uncalibrated"


def test_pseudonym_strings_cannot_establish_distinct_people() -> None:
    # Different strings pass the draft check, whoever they belong to: D19 stays a private,
    # human verification and this check must not be read as person-level disjointness.
    data = _data()
    data["calibration_identities"] = ["SYN-301", "SYN-302"]
    data["evaluation_identities"] = ["SYN-401"]
    assert parse_analysis_plan(data).calibration_identities == ["SYN-301", "SYN-302"]
    data["evaluation_identities"] = ["SYN-301"]
    with pytest.raises(ManifestError, match="disjoint"):
        parse_analysis_plan(data)


# Non-regression of pins, gates and the CPU/no-recogniser boundary ------------------------------


def test_gates_provenance_and_controls_are_unchanged() -> None:
    record = load_readiness(ROOT / "readiness/wan21-i2v-baseline.yaml")
    assert [g.gate_id for g in record.gates] == list(GATE_IDS)
    assert len(GATE_IDS) == 7
    assert {g.status for g in record.gates} == {"pending"}
    assert record.execution_controls.use_prompt_extend is False
    inventory = load_provenance(ROOT / "provenance/model-candidates.yaml")
    candidate = next(
        c for c in inventory.candidates if c.candidate_id == record.target.candidate_id
    )
    assert candidate.execution_readiness == "not_ready"


def test_decisions_d13_d14_d15_stay_unsettled_in_the_example_plan() -> None:
    plan_model = parse_analysis_plan(_data())
    assert plan_model.status == "draft"
    text = (ROOT / "docs/baseline-analysis-preregistration.md").read_text(encoding="utf-8")
    for decision in ("D13", "D14"):
        row = next(line for line in text.splitlines() if line.startswith(f"| {decision} "))
        assert "**Pending**" in row


def test_source_imports_no_recogniser_detector_or_imaging_library() -> None:
    forbidden = {"insightface", "dlib", "cv2", "facenet_pytorch", "mediapipe", "onnxruntime", "PIL"}
    found = set()
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
    assert not found & forbidden
