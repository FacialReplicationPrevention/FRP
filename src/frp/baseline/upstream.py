"""Placeholder for the live upstream Wan 2.1 backend. **Disabled in this release.**

This module imports no ML, GPU, imaging or ``wan`` package, performs no work at import and
discovers no checkpoint. :class:`UpstreamWan21Backend` implements the
:class:`~frp.baseline.backend.Wan21Backend` protocol only far enough to refuse safely:
``check_available`` raises :class:`~frp.baseline.backend.LiveExecutionDisabled`, so the executor
records ``live_execution_disabled`` before any authorisation-dependent step could load anything.

Pending integration point (not implemented, not verified). Per Research 005, at Wan-Video/Wan2.1
``9737cba9c1c3c4d04b33fcad41c111989865d315`` the flow a future, separately reviewed change would
have to follow is:

* construct ``wan.WanI2V(config=WAN_CONFIGS["i2v-14B"], checkpoint_dir=<verified dir>,
  device_id=..., rank=0, t5_fsdp=False, dit_fsdp=False, use_usp=False, t5_cpu=False)``; its
  constructor builds the models from local paths and ``WanModel.from_pretrained(checkpoint_dir)``
  with a local directory, so a download must be impossible by construction (offline environment);
* call ``generate(input_prompt, img, max_area=..., frame_num=..., shift=..., sample_solver=...,
  sampling_steps=..., guide_scale=..., n_prompt="", seed=..., offload_model=...)`` with a
  non-negative ``seed`` (upstream draws a random seed for a negative one) and ``n_prompt=""`` so
  the config default negative prompt is used;
* never import ``wan.utils.prompt_extend`` or ``dashscope`` (the upstream ``generate.py`` imports
  them at module level, so ``generate.py`` must not be imported or run);
* the upstream flow keeps no hook for the observations in :mod:`frp.baseline.backend`; capturing
  tensor metadata and CFG branch order needs instrumentation whose own effect on the run is
  unreviewed. None of this has been run, and no signature above has been exercised by FRP.
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
