"""Deterministic, CPU-only simulated executor and evaluators for exercising the pipeline.

**Every value produced here is a synthetic test fixture.** No model is loaded, no image or
video is generated, no face is detected and no embedding is computed. Outcomes follow fixed
modular rules over (group index, variant position, frame position) and fixture scores are
derived from SHA-256 hashes of run ids. Fixture values do not depend on the variant's
conditioning, so any difference between variants is an artefact of these rules and says
nothing about any model or safeguard.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from frp.manifest import ExperimentManifest
from frp.pipeline import execute_plan
from frp.planner import PlannedRun, generate_run_plan
from frp.results import (
    ArtefactRef,
    ExecutionRecord,
    ExecutorInfo,
    FaceEvaluatorInfo,
    FaceStatus,
    FrameEvaluation,
    QualityEvaluation,
    QualityEvaluatorInfo,
    ResultSet,
    ResultValidationError,
    verify_results_against_plan,
)
from frp.variants import VARIANT_ORDER

# Candidate frame set for 81-frame video from Experiment 002, used only when the manifest
# leaves both frame_indices and frame_count unset. Recorded in results as "simulation_default".
SIMULATION_DEFAULT_FRAME_INDICES: Final = (0, 20, 40, 60, 80)
SIMULATED_QUALITY_SCALE: Final = (1.0, 5.0)
SIMULATED_MODEL_FAMILY: Final = "wan2.1-i2v"
_SIMILARITY_FIXTURE_RANGE: Final = (0.1, 0.9)


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """Fixed outcome rules. A ``*_period`` of ``n`` hits a run (or frame) when the sum of its
    1-based group index, 0-based variant position (A=0..D=3) and, for frame rules, 0-based
    frame position is divisible by ``n``. Frame rules apply in order: error, multiple, absent,
    low_quality; quality rules in order: not_evaluated, error, unscorable.
    """

    name: str
    description: str
    run_failure_period: int | None = None
    face_error_period: int | None = None
    face_multiple_period: int | None = None
    face_absent_period: int | None = None
    face_low_quality_period: int | None = None
    quality_not_evaluated_period: int | None = None
    quality_error_period: int | None = None
    quality_unscorable_period: int | None = None
    interrupt_after_fraction: float | None = None


SCENARIOS: Final = MappingProxyType(
    {
        scenario.name: scenario
        for scenario in (
            SimulationScenario(
                "mixed",
                "Deterministic mix of failed runs, interrupted execution, face-status outcomes "
                "and missing quality scores.",
                run_failure_period=5,
                face_error_period=12,
                face_multiple_period=7,
                face_absent_period=5,
                face_low_quality_period=11,
                quality_not_evaluated_period=6,
                quality_error_period=7,
                quality_unscorable_period=8,
                interrupt_after_fraction=0.9,
            ),
            SimulationScenario("all-valid", "Every run succeeds; every face and score is valid."),
            SimulationScenario(
                "absent-face", "Some frames contain no detectable face.", face_absent_period=3
            ),
            SimulationScenario(
                "multiple-faces", "Some frames contain more than one face.", face_multiple_period=3
            ),
            SimulationScenario(
                "evaluator-error",
                "Face and quality evaluators report errors for some outputs.",
                face_error_period=4,
                quality_error_period=5,
            ),
            SimulationScenario(
                "missing-quality",
                "Some video-quality scores are unavailable or unscorable.",
                quality_not_evaluated_period=3,
                quality_unscorable_period=4,
            ),
            SimulationScenario("failed-run", "Some runs fail to execute.", run_failure_period=5),
            SimulationScenario(
                "incomplete",
                "The experiment is interrupted after 75% of planned runs.",
                interrupt_after_fraction=0.75,
            ),
        )
    }
)
DEFAULT_SCENARIO: Final = "mixed"


def _hits(period: int | None, *parts: int) -> bool:
    return period is not None and sum(parts) % period == 0


def _fixture_unit(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _variant_position(run: PlannedRun) -> int:
    return VARIANT_ORDER.index(run.variant)


class SimulatedExecutor:
    """Pretends to generate a video: returns an opaque ``simulated://`` reference, no media."""

    def __init__(self, scenario: SimulationScenario) -> None:
        self._scenario = scenario
        self._runs: dict[str, PlannedRun] = {}

    @property
    def info(self) -> ExecutorInfo:
        return ExecutorInfo(
            name="frp-simulated-executor",
            revision="1",
            model_family=SIMULATED_MODEL_FAMILY,
            simulated=True,
        )

    def execute(self, run: PlannedRun) -> ExecutionRecord:
        if _hits(self._scenario.run_failure_period, run.group_index, _variant_position(run)):
            return ExecutionRecord(
                status="failed", artefact=None, failure_category="other", gpu_seconds=None
            )
        token = hashlib.sha256(f"simulated-artefact|{run.run_id}".encode()).hexdigest()[:16]
        artefact = ArtefactRef(uri=f"simulated://artefact/{token}")
        self._runs[artefact.uri] = run
        # gpu_seconds stays null: a simulated runtime would be a fabricated hardware cost.
        return ExecutionRecord(
            status="succeeded", artefact=artefact, failure_category=None, gpu_seconds=None
        )

    def resolve(self, artefact: ArtefactRef) -> PlannedRun:
        """Simulation-only lookup so fixture evaluators can apply the scenario rules."""
        return self._runs[artefact.uri]


class SimulatedFaceEvaluator:
    def __init__(self, scenario: SimulationScenario, executor: SimulatedExecutor) -> None:
        self._scenario = scenario
        self._executor = executor

    @property
    def info(self) -> FaceEvaluatorInfo:
        settings = json.dumps({"scenario": self._scenario.name}, sort_keys=True)
        return FaceEvaluatorInfo(
            name="frp-simulated-face-evaluator",
            revision="1",
            settings_sha256=hashlib.sha256(settings.encode("utf-8")).hexdigest(),
            simulated=True,
        )

    def _status(self, run: PlannedRun, frame_position: int) -> FaceStatus:
        s = self._scenario
        parts = (run.group_index, _variant_position(run), frame_position)
        rules: tuple[tuple[int | None, FaceStatus], ...] = (
            (s.face_error_period, "error"),
            (s.face_multiple_period, "multiple"),
            (s.face_absent_period, "absent"),
            (s.face_low_quality_period, "low_quality"),
        )
        for period, status in rules:
            if _hits(period, *parts):
                return status
        return "valid"

    def evaluate(
        self, artefact: ArtefactRef, identity_pseudonym: str, frame_indices: Sequence[int]
    ) -> tuple[FrameEvaluation, ...]:
        del identity_pseudonym  # no reference image exists in simulation
        run = self._executor.resolve(artefact)
        low, high = _SIMILARITY_FIXTURE_RANGE
        frames = []
        for position, frame_index in enumerate(frame_indices):
            status = self._status(run, position)
            similarity = None
            if status == "valid":
                unit = _fixture_unit("simulated-similarity", run.run_id, frame_index)
                similarity = round(low + (high - low) * unit, 3)
            frames.append(
                FrameEvaluation(frame_index=frame_index, face_status=status, similarity=similarity)
            )
        return tuple(frames)


class SimulatedQualityEvaluator:
    def __init__(self, scenario: SimulationScenario, executor: SimulatedExecutor) -> None:
        self._scenario = scenario
        self._executor = executor

    @property
    def info(self) -> QualityEvaluatorInfo:
        return QualityEvaluatorInfo(
            name="frp-simulated-quality-evaluator",
            revision="simulated-rubric-1",
            scale_min=SIMULATED_QUALITY_SCALE[0],
            scale_max=SIMULATED_QUALITY_SCALE[1],
            simulated=True,
        )

    def evaluate(self, artefact: ArtefactRef) -> QualityEvaluation:
        run = self._executor.resolve(artefact)
        s = self._scenario
        parts = (run.group_index, _variant_position(run))
        if _hits(s.quality_not_evaluated_period, *parts):
            return QualityEvaluation(status="not_evaluated", score=None)
        if _hits(s.quality_error_period, *parts):
            return QualityEvaluation(status="error", score=None)
        if _hits(s.quality_unscorable_period, *parts):
            return QualityEvaluation(status="unscorable", score=None)
        low, high = SIMULATED_QUALITY_SCALE
        steps = int(high - low) + 1
        score = low + int(_fixture_unit("simulated-quality", run.run_id) * steps)
        return QualityEvaluation(status="scored", score=float(score))


def default_frame_indices(frame_count: int | None) -> tuple[int, ...]:
    """Simulation default: Experiment 002's 0/20/40/60/80 set for 81 frames, scaled
    proportionally to ``frame_count`` (always 4n+1) when the manifest sets it."""
    if frame_count is None:
        return SIMULATION_DEFAULT_FRAME_INDICES
    return tuple(sorted({k * (frame_count - 1) // 4 for k in range(5)}))


def simulate_experiment(
    manifest: ExperimentManifest, scenario_name: str = DEFAULT_SCENARIO
) -> ResultSet:
    """Run the full simulated pipeline for a validated manifest and return result records."""
    scenario = SCENARIOS.get(scenario_name)
    if scenario is None:
        raise ResultValidationError(["unknown simulation scenario"])
    plan = generate_run_plan(manifest)
    if manifest.frame_indices is not None:
        frame_indices, source = tuple(manifest.frame_indices), "manifest"
    else:
        frame_indices = default_frame_indices(manifest.frame_count)
        source = "simulation_default"
    max_runs = None
    if scenario.interrupt_after_fraction is not None:
        max_runs = int(len(plan.runs) * scenario.interrupt_after_fraction)
    executor = SimulatedExecutor(scenario)
    results = execute_plan(
        plan,
        executor,
        SimulatedFaceEvaluator(scenario, executor),
        SimulatedQualityEvaluator(scenario, executor),
        frame_indices=frame_indices,
        frame_indices_source=source,
        frame_count=manifest.frame_count,
        simulation_scenario=scenario.name,
        max_runs=max_runs,
    )
    verify_results_against_plan(results, plan, manifest)
    return results
