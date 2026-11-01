"""Synthetic, procedurally generated demonstration store for the private review viewer.

**SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE.** Nothing here is a face, a person, a
portrait, a model output or a measurement. The "reference" stills are nested coloured rectangles
and the "videos" are a coloured square moving over a gradient. The "similarities" and quality
"scores" are SHA-256-derived fixture numbers attached by synthetic evaluators marked
``simulated``. They exercise the evaluation pipeline and the viewer's handling of every face
status, failed and retried attempts, an unexecuted run and missing media.

The generator is deterministic, so :func:`demo_frame_digests` can prove that a store labelled
``synthetic`` contains only these procedural frames (see :mod:`frp.review.access`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Final

from frp.baseline.aggregation import BaselineSummary, aggregate_baseline
from frp.baseline.evaluation import evaluate_baseline_results
from frp.baseline.manifest import BaselineManifest, parse_baseline_manifest
from frp.baseline.planner import BaselinePlan, generate_baseline_plan
from frp.baseline.protocol import ROLE_CLAIMS
from frp.baseline.results import (
    FAILURE_CATEGORY_FOR_DETAIL,
    BaselineAttempt,
    BaselineResultSet,
    ConditioningSummary,
    FailureDetail,
    TensorMeta,
    UnexecutedRun,
)
from frp.results import (
    QUALITY_NOT_EVALUATED,
    ArtefactRef,
    ExecutionRecord,
    ExecutorInfo,
    FaceEvaluatorInfo,
    FaceStatus,
    FrameEvaluation,
    QualityEvaluation,
    QualityEvaluatorInfo,
    frames_with_status,
)
from frp.review.png import encode_png_rgb
from frp.review.store import MediaEntry, ReviewStore, build_catalogue, new_media_id

DEMO_SCENARIO: Final = "synthetic-review-demo"
DEMO_STORE_ID: Final = "synthetic-review-demo"
DEMO_EXPERIMENT_ID: Final = "FRP-REVIEW-DEMO-SYNTHETIC"
WIDTH: Final = 112
HEIGHT: Final = 64
FRAME_COUNT: Final = 17
FRAME_INDICES: Final = (0, 4, 8, 12, 16)
PLAYBACK_FPS: Final = 8
# Demo-only analysis parameters; not preregistered values (Experiment 003, decisions 2 and 4).
DEMO_MIN_VALID_LATER_FRAMES: Final = 1
DEMO_ATTEMPT_SELECTION: Final = "first_attempt"
_ARTEFACT_BASE: Final = "private://synthetic-review-demo"
_T0: Final = datetime(2026, 1, 1, tzinfo=UTC)
_PALETTES: Final = {
    1: ((20, 60, 140), (60, 170, 200), (240, 200, 40)),
    2: ((120, 40, 20), (230, 140, 60), (40, 200, 120)),
    3: ((20, 90, 40), (140, 210, 120), (200, 60, 160)),
}
SIMULATED_NOTICE: Final = (
    "SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE. Procedurally generated, non-biometric "
    "demo content; fixture numbers describe no model, person or safeguard."
)

# Planned scenario per run: attempts as (outcome, failure detail), then per-frame face statuses
# for succeeded attempts, then whether the output media is imported into the store.
_ATTEMPTS: Final[dict[int, tuple[FailureDetail | None, ...]]] = {
    1: (None,),
    2: (None,),
    3: ("timeout", None),
    4: (None,),
    5: ("output_contract_violation",),
}
_FACE_PATTERNS: Final[dict[int, tuple[FaceStatus, ...]]] = {
    1: ("valid",) * 5,
    2: ("valid", "absent", "multiple", "low_quality", "error"),
    3: ("valid", "valid", "valid", "absent", "valid"),
    4: ("valid",) * 5,
}
_UNSCORABLE_RUNS: Final = frozenset({2})
_MEDIA_NOT_IMPORTED: Final = frozenset({4})


def demo_manifest() -> BaselineManifest:
    return parse_baseline_manifest(
        {
            "schema_version": "baseline-0.1-draft",
            "protocol": "wan2.1-i2v-baseline",
            "experiment_id": DEMO_EXPERIMENT_ID,
            "status": "planned",
            "run_role": "baseline",
            "identities": [
                {"pseudonym": f"SYN-{n}", "identity_split": "evaluation"} for n in (201, 202, 203)
            ],
            "prompts": [
                {"id": "P01-pattern", "text": "A coloured square drifts across a gradient."}
            ],
            "seeds": [11, 22],
            "upstream_repository": "Wan-Video/Wan2.1",
            "upstream_commit_sha": None,
            "checkpoint": "Wan-AI/Wan2.1-I2V-14B-480P",
            "checkpoint_revision": None,
            "checkpoint_hashes": None,
            "software_environment_hash": None,
            "gpu_model": None,
            "use_prompt_extend": False,
            "clip_conditioning": "original",
            "vae_first_frame_conditioning": "original",
            "adapters": "none",
            "remote_inference_services": "none",
            "negative_prompt_policy": "upstream_config_default",
            "prompt_policy": "neutral_motion_only",
            "generator": "upstream_seeded_torch_cuda_generator",
            "artefact_storage": "private_only",
            "consent_record_location": "private_only",
            "image_count_per_identity": 1,
            "prompt_template_version": None,
            "sampler": None,
            "sampling_steps": None,
            "guidance_scale": None,
            "sample_shift": None,
            "frame_count": FRAME_COUNT,
            "resolution": None,
            "precision": None,
            "offload_model": None,
            "image_preprocessing_version": None,
            "frame_indices": list(FRAME_INDICES),
            "face_evaluator_revision": None,
            "face_detection_settings": None,
            "calibration_dataset_version": None,
            "quality_rubric_version": None,
            "analysis_plan_version": None,
        }
    )


def _artefact_uri(run_id: str, attempt_index: int) -> str:
    return f"{_ARTEFACT_BASE}/{run_id}/attempt-{attempt_index:02d}"


def _fixture_number(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return round(0.1 + 0.8 * int.from_bytes(digest[:4], "big") / 0xFFFFFFFF, 4)


def _run_number(run_id: str) -> int:
    return int(run_id.rsplit("-R", 1)[1])


class DemoFaceEvaluator:
    """Synthetic face evaluator: fixed statuses per demo run, SHA-256 fixture similarities."""

    info = FaceEvaluatorInfo(
        name="synthetic-demo-face", revision="0.1", settings_sha256=None, simulated=True
    )

    def evaluate(
        self, artefact: ArtefactRef, identity_pseudonym: str, frame_indices: Sequence[int]
    ) -> tuple[FrameEvaluation, ...]:
        run_id = artefact.uri.split("/")[-2]
        pattern = _FACE_PATTERNS[_run_number(run_id)]
        return tuple(
            FrameEvaluation(
                frame_index=index,
                face_status=status,
                similarity=_fixture_number(artefact.uri, index) if status == "valid" else None,
            )
            for index, status in zip(frame_indices, pattern, strict=True)
        )


class DemoQualityEvaluator:
    """Synthetic quality evaluator on a simulated 1-5 scale; one run is ``unscorable``."""

    info = QualityEvaluatorInfo(
        name="synthetic-demo-quality", revision="0.1", scale_min=1.0, scale_max=5.0, simulated=True
    )

    def evaluate(self, artefact: ArtefactRef) -> QualityEvaluation:
        if _run_number(artefact.uri.split("/")[-2]) in _UNSCORABLE_RUNS:
            return QualityEvaluation(status="unscorable", score=None)
        return QualityEvaluation(
            status="scored", score=float(1 + int(_fixture_number(artefact.uri) * 5) % 5)
        )


def _conditioning() -> ConditioningSummary:
    meta = TensorMeta(shape=(1, 1), dtype="synthetic", device="cpu")
    return ConditioningSummary(
        same_reference_on_both_routes=True,
        clip_features=meta,
        vae_first_frame_condition=meta,
        positive_branch_calls=1,
        negative_branch_calls=1,
        branches_share_image_conditioning=True,
        clip_route_feeds_denoiser=True,
    )


def demo_unevaluated_results(plan: BaselinePlan) -> BaselineResultSet:
    """The scenario's attempts and unexecuted runs, with every evaluation ``not_evaluated``."""
    attempts = []
    unexecuted = []
    for run in plan.runs:
        details = _ATTEMPTS.get(run.run_index)
        if details is None:
            unexecuted.append(UnexecutedRun(run_id=run.run_id, reason="halted_after_failure"))
            continue
        for attempt_index, detail in enumerate(details, 1):
            started = _T0 + timedelta(minutes=10 * run.run_index + attempt_index)
            execution = (
                ExecutionRecord(
                    status="succeeded",
                    artefact=ArtefactRef(uri=_artefact_uri(run.run_id, attempt_index)),
                    failure_category=None,
                    gpu_seconds=None,
                )
                if detail is None
                else ExecutionRecord(
                    status="failed",
                    artefact=None,
                    failure_category=FAILURE_CATEGORY_FOR_DETAIL[detail],
                    gpu_seconds=None,
                )
            )
            attempts.append(
                BaselineAttempt(
                    run_id=run.run_id,
                    attempt_index=attempt_index,
                    run_role=run.run_role,
                    identity_index=run.identity_index,
                    prompt_index=run.prompt_index,
                    seed=run.seed,
                    generation_controls_sha256=run.generation_controls_sha256,
                    started_at=started,
                    finished_at=started + timedelta(seconds=1),
                    wall_seconds=1.0,
                    execution=execution,
                    failure_detail=detail,
                    conditioning=_conditioning() if detail is None else None,
                    cleanup_ok=True,
                    frames=frames_with_status(FRAME_INDICES, "not_evaluated"),
                    quality=QUALITY_NOT_EVALUATED,
                )
            )
    return BaselineResultSet(
        result_schema_version="baseline-0.1-draft",
        protocol="wan2.1-i2v-baseline",
        run_role=plan.run_role,
        claim_scope=ROLE_CLAIMS[plan.run_role].claim_scope,
        simulated=True,
        simulation_scenario=DEMO_SCENARIO,
        experiment_id=plan.experiment_id,
        plan_schema_version="baseline-0.1-draft",
        manifest_sha256=plan.manifest_sha256,
        generation_controls_sha256=plan.generation_controls_sha256,
        frame_indices=FRAME_INDICES,
        executor=ExecutorInfo(
            name="synthetic-review-demo", revision="0.1", model_family="wan2.1-i2v", simulated=True
        ),
        face_evaluator=None,
        quality_evaluator=None,
        provenance=None,
        stop_reason="halted_after_failure",
        attempts=tuple(attempts),
        unexecuted=tuple(unexecuted),
    )


def _gradient_frame(
    palette: tuple[tuple[int, int, int], ...], x: int, y: int, size: int
) -> list[bytes]:
    top, bottom, square = palette
    rows = []
    for row_index in range(HEIGHT):
        t = row_index / (HEIGHT - 1)
        background = bytes(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        row = bytearray(background * WIDTH)
        if y <= row_index < y + size:
            x0, x1 = max(0, x), min(WIDTH, x + size)
            row[x0 * 3 : x1 * 3] = bytes(square) * (x1 - x0)
        rows.append(bytes(row))
    return rows


def _reference_still(identity_index: int) -> bytes:
    palette = _PALETTES[identity_index]
    rows = [bytearray(bytes(palette[0]) * WIDTH) for _ in range(HEIGHT)]
    for depth, colour in enumerate((palette[1], palette[2], palette[0], palette[1])):
        inset = 6 + depth * 7
        for row in rows[inset : HEIGHT - inset]:
            row[inset * 3 : (WIDTH - inset) * 3] = bytes(colour) * (WIDTH - 2 * inset)
    return encode_png_rgb(WIDTH, HEIGHT, [bytes(r) for r in rows])


def _output_frames(identity_index: int, seed: int, attempt_index: int) -> list[bytes]:
    palette = _PALETTES[identity_index]
    size = 14 + 4 * attempt_index
    step = 3 if seed % 2 else 5
    frames = []
    for frame in range(FRAME_COUNT):
        x = (frame * step) % (WIDTH - size)
        y = (HEIGHT - size) // 2 + (frame % 4) - 2
        frames.append(encode_png_rgb(WIDTH, HEIGHT, _gradient_frame(palette, x, y, size)))
    return frames


@lru_cache(maxsize=1)
def _demo_media() -> dict[tuple[str, str], tuple[bytes, ...]]:
    plan = generate_baseline_plan(demo_manifest())
    media: dict[tuple[str, str], tuple[bytes, ...]] = {}
    for identity_index in sorted({run.identity_index for run in plan.runs}):
        media[("reference", str(identity_index))] = (_reference_still(identity_index),)
    for run in plan.runs:
        for attempt_index, detail in enumerate(_ATTEMPTS.get(run.run_index, ()), 1):
            if detail is None and run.run_index not in _MEDIA_NOT_IMPORTED:
                media[("output", _artefact_uri(run.run_id, attempt_index))] = tuple(
                    _output_frames(run.identity_index, run.seed, attempt_index)
                )
    return media


@lru_cache(maxsize=1)
def demo_frame_digests() -> frozenset[str]:
    """SHA-256 of every frame the procedural demo generator can produce."""
    return frozenset(
        hashlib.sha256(frame).hexdigest() for frames in _demo_media().values() for frame in frames
    )


@dataclass(frozen=True, slots=True)
class DemoStore:
    manifest: BaselineManifest
    plan: BaselinePlan
    unevaluated: BaselineResultSet
    results: BaselineResultSet
    summary: BaselineSummary
    items: int


def create_demo_store(root: Path) -> DemoStore:
    """Generate the synthetic results, evaluate and aggregate them, and write a review store."""
    manifest = demo_manifest()
    plan = generate_baseline_plan(manifest)
    unevaluated = demo_unevaluated_results(plan)
    results = evaluate_baseline_results(
        unevaluated,
        plan,
        face_evaluator=DemoFaceEvaluator(),
        quality_evaluator=DemoQualityEvaluator(),
        manifest=manifest,
    )
    summary = aggregate_baseline(
        results,
        plan,
        min_valid_later_frames=DEMO_MIN_VALID_LATER_FRAMES,
        attempt_selection=DEMO_ATTEMPT_SELECTION,
    )
    store = ReviewStore(root)
    store.create()
    registry: dict[str, MediaEntry] = {}
    references: dict[int, str | None] = {}
    outputs: dict[str, str | None] = {}
    for (kind, key), frames in _demo_media().items():
        media_id = new_media_id()
        digests = tuple(store.write_media_frame(media_id, i, png) for i, png in enumerate(frames))
        registry[media_id] = MediaEntry(
            kind="still" if kind == "reference" else "frame_sequence",
            width=WIDTH,
            height=HEIGHT,
            frame_sha256=digests,
        )
        if kind == "reference":
            references[int(key)] = media_id
        else:
            outputs[key] = media_id
    catalogue = build_catalogue(
        results,
        plan,
        store_id=DEMO_STORE_ID,
        content_class="synthetic",
        storage_approval_reference=None,
        reference_media=references,
        output_media=outputs,
        media=registry,
        playback_fps=PLAYBACK_FPS,
    )
    store.write_catalogue(catalogue)
    return DemoStore(manifest, plan, unevaluated, results, summary, len(catalogue.items))


__all__ = [
    "DEMO_SCENARIO",
    "FRAME_COUNT",
    "FRAME_INDICES",
    "SIMULATED_NOTICE",
    "DemoFaceEvaluator",
    "DemoQualityEvaluator",
    "DemoStore",
    "create_demo_store",
    "demo_frame_digests",
    "demo_manifest",
    "demo_unevaluated_results",
]
