"""Default live-backend placeholder for the Wan 2.1 baseline. **Disabled in this release.**

This module imports no ML, GPU, imaging or ``wan`` package, performs no work at import and
discovers no checkpoint. :class:`UpstreamWan21Backend` implements the
:class:`~frp.baseline.backend.Wan21Backend` protocol only far enough to refuse safely:
``check_available`` raises :class:`~frp.baseline.backend.LiveExecutionDisabled`, so the executor
records ``live_execution_disabled`` before any authorisation-dependent step could load anything.

The source-mapped integration is :class:`frp.baseline.wan21_adapter.Wan21UpstreamAdapter` over
:class:`frp.baseline.wan21_runtime.TorchWanRuntime` (Milestone 004 PR 3B). No command, default or
CI path constructs it; it is CPU-tested only against a fake upstream and has never been run. See
``docs/wan21-private-execution-runbook.md`` for the approvals it still needs.
"""

from __future__ import annotations

from frp.baseline.backend import (
    BackendInfo,
    GenerationOutput,
    GenerationRequest,
    LiveExecutionDisabled,
    StopSignal,
)
from frp.baseline.preflight import VerifiedCheckpoint

UPSTREAM_BACKEND_NAME = "wan21-upstream-disabled"


class UpstreamWan21Backend:
    """Refuses everything: the live integration is not wired, reviewed or authorised."""

    @property
    def info(self) -> BackendInfo:
        return BackendInfo(name=UPSTREAM_BACKEND_NAME, revision="disabled", live=True)

    def check_available(self) -> None:
        raise LiveExecutionDisabled("the live Wan 2.1 backend is disabled in this release")

    def environment_sha256(self) -> str:
        raise LiveExecutionDisabled("the live Wan 2.1 backend is disabled in this release")

    def load(self, checkpoint: VerifiedCheckpoint) -> None:
        raise LiveExecutionDisabled("the live Wan 2.1 backend is disabled in this release")

    def generate(self, request: GenerationRequest, stop: StopSignal) -> GenerationOutput:
        raise LiveExecutionDisabled("the live Wan 2.1 backend is disabled in this release")

    def cleanup(self) -> None:
        return None

    def close(self) -> None:
        return None
