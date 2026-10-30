"""Executor contract for the baseline. ``frp.interfaces.RunExecutor(PlannedRun)`` is unchanged.

:class:`BaselineExecutor` consumes a :class:`~frp.baseline.planner.BaselinePlannedRun` and is told
the attempt index, so a retry is a new attempt with a new artefact and never overwrites an earlier
one. The face and quality evaluator contracts in :mod:`frp.interfaces` are model-agnostic (they take
an artefact reference only) and are reused unchanged.

Outcomes versus refusals:

* ``execute`` returns a :class:`BaselineExecutionOutcome` once generation was attempted, whether it
  succeeded or failed. A success carries an artefact reference and verified conditioning metadata;
  a failure never carries an artefact.
* ``execute`` raises :class:`ExecutionRefused` when it declined to start (not execution ready, not
  authorised, dependency, provenance or weight checks failed). Nothing was loaded or generated,
  so it is recorded as an *unexecuted* run, not as an attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from frp.baseline.planner import BaselinePlannedRun
from frp.baseline.results import (
    ConditioningSummary,
    ExecutionProvenance,
    FailureDetail,
    RefusalReason,
)
from frp.results import ExecutionRecord, ExecutorInfo


class ExecutionRefused(Exception):
    """The executor declined to start. ``code`` is a fixed reason; no free text is kept."""

    def __init__(self, code: RefusalReason) -> None:
        self.code: RefusalReason = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class BaselineExecutionOutcome:
    """What one attempt produced: an execution record plus private structured diagnostics."""

    execution: ExecutionRecord
    failure_detail: FailureDetail | None
    started_at: datetime
    finished_at: datetime
    wall_seconds: float
    conditioning: ConditioningSummary | None
    cleanup_ok: bool


class BaselineExecutor(Protocol):
    """Runs one attempt of one planned baseline run.

    Must either return a succeeded outcome (artefact reference and conditioning metadata), a failed
    outcome (failure category and detail, no artefact), or raise :class:`ExecutionRefused`. Must
    apply the original reference to both the CLIP and VAE first-frame routes, never enable prompt
    extension, never use a remote service, and must not return media, tensors or embeddings.
    """

    @property
    def info(self) -> ExecutorInfo: ...

    @property
    def verified_provenance(self) -> ExecutionProvenance | None:
        """Local verification evidence once preflight has passed, else ``None``."""
        ...

    def execute(self, run: BaselinePlannedRun, attempt_index: int) -> BaselineExecutionOutcome: ...

    def close(self) -> None: ...
