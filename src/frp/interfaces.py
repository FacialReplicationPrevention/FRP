"""Adapter contracts for run execution, face/identity evaluation and video-quality evaluation.

These are structural ``Protocol`` types: an adapter only needs matching attributes and methods,
not a base class. This module imports no ML, imaging or GPU libraries, so real adapters (for
example a future Wan 2.1 executor or an ArcFace-family evaluator) can live in separate optional
packages without changing the orchestrator, result schema or reports.

Model-family scope: :class:`RunExecutor` consumes the Wan 2.1 A/B/C/D :class:`PlannedRun`.
Another model family would need its own reviewed protocol and plan type; the evaluator
contracts below take only an opaque artefact reference and are model-agnostic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from frp.planner import PlannedRun
from frp.results import (
    ArtefactRef,
    ExecutionRecord,
    ExecutorInfo,
    FaceEvaluatorInfo,
    FrameEvaluation,
    QualityEvaluation,
    QualityEvaluatorInfo,
)


class RunExecutor(Protocol):
    """Generates one planned run and returns provenance, status and an artefact *reference*.

    Must return status ``succeeded`` (with an artefact reference) or ``failed`` (with a
    failure category). ``not_executed`` is assigned only by the orchestrator. Implementations
    must apply the run's CLIP and VAE first-frame conditioning sources exactly as planned and
    must not return media, tensors or embeddings.
    """

    @property
    def info(self) -> ExecutorInfo: ...

    def execute(self, run: PlannedRun) -> ExecutionRecord: ...


class FaceIdentityEvaluator(Protocol):
    """Detects faces at the requested frames and scores identity similarity for valid faces.

    Receives the identity pseudonym (to locate the private reference image) but not the
    variant. Must return exactly one :class:`FrameEvaluation` per requested frame index, in
    order. Detection outcome (``face_status``) is separate from the numerical similarity,
    which is present only for ``valid`` faces.
    """

    @property
    def info(self) -> FaceEvaluatorInfo: ...

    def evaluate(
        self, artefact: ArtefactRef, identity_pseudonym: str, frame_indices: Sequence[int]
    ) -> Sequence[FrameEvaluation]: ...


class VideoQualityEvaluator(Protocol):
    """Scores video utility independently of identity, on the declared rubric scale.

    Receives only the artefact reference, so the contract supports blinded evaluation.
    Unscorable or unavailable outputs must be reported by status, never by an invented score.
    """

    @property
    def info(self) -> QualityEvaluatorInfo: ...

    def evaluate(self, artefact: ArtefactRef) -> QualityEvaluation: ...
