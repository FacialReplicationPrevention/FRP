"""Backend contract and conditioning-trace checks for the Wan 2.1 baseline executor.

A *backend* is the only component that may touch ``torch``, CUDA or the upstream ``wan`` package;
the executor in :mod:`frp.baseline.executor` talks to it through the structural protocol below,
which is what makes the whole execution boundary testable on CPU with a fake.

What a backend must report is **metadata only**: shape/dtype/device of tensors, which reference
token each image route consumed, and the order and tensor metadata of the positive/negative
classifier-free-guidance (CFG) calls. Never pixels, latents, embeddings, prompts or media paths.

Single-reference guarantee. :class:`GenerationRequest` has exactly one ``reference`` field and no
way to name a second image or a ``use_prompt_extend`` switch, so the request itself cannot ask for
different CLIP and VAE sources or for prompt extension. The checks in
:func:`verify_conditioning` then compare what the backend *observed* with the request. For the
pinned upstream flow this mirrors Research 005: ``WanI2V.generate(input_prompt, img, ...)`` takes a
single ``img`` that feeds both ``self.clip.visual`` and ``self.vae.encode``, and ``arg_c`` and
``arg_null`` share ``clip_fea`` and ``y``. A fake backend satisfying these checks proves the
executor's control flow, **not** that the live integration behaves this way; that remains
unverified until an authorised run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from frp.baseline.preflight import VerifiedCheckpoint
from frp.baseline.protocol import WAN21_SPATIAL_MULTIPLE
from frp.baseline.results import ConditioningSummary, TensorMeta

StopReasonCode = Literal["budget_stop", "operator_abort"]
CfgBranch = Literal["positive", "negative"]
VIDEO_CHANNELS: Final = 3


class StopSignal(Protocol):
    """Human- or budget-controlled stop request, polled before and during an attempt."""

    def reason(self) -> StopReasonCode | None: ...


class BackendError(Exception):
    """Base class for backend failures. Messages are never recorded (they may leak paths)."""


class BackendUnavailable(BackendError):
    """Optional GPU dependencies, files or permissions are absent."""


class LiveExecutionDisabled(BackendUnavailable):
    """The live upstream backend is not wired in this release."""


class ModelLoadError(BackendError):
    """Loading the model failed."""


class GenerationInterrupted(BackendError):
    """Generation stopped on a stop signal; carries the signal's reason."""

    def __init__(self, reason: StopReasonCode) -> None:
        self.reason = reason
        super().__init__(reason)


class GenerationTimeout(BackendError):
    """The approved per-attempt time cap was reached."""


class GenerationResourceExhausted(BackendError):
    """Out of GPU or host memory or storage."""


@dataclass(frozen=True, slots=True)
class BackendInfo:
    name: str
    revision: str
    live: bool  # False for CPU mocks: a mock's success is not a Wan 2.1 inference result


@dataclass(frozen=True, slots=True)
class ReferenceHandle:
    """Opaque handle for one private reference image. The location never appears in a repr."""

    token: str
    location: str = field(repr=False)


class ReferenceProvider(Protocol):
    """Resolves an identity pseudonym to its single private reference image."""

    def reference_for(self, identity_pseudonym: str) -> ReferenceHandle:
        """Raise ``LookupError`` if there is no reference for this identity."""
        ...


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Everything a backend needs for one attempt. Deliberately has no prompt-extension field."""

    run_id: str
    attempt_index: int
    reference: ReferenceHandle
    prompt_text: str = field(repr=False)
    seed: int
    max_area: int
    frame_count: int
    sample_shift: float
    sample_solver: str
    sampling_steps: int
    guide_scale: float
    offload_model: bool
    output_uri: str = field(repr=False)
    deadline_seconds: float


@dataclass(frozen=True, slots=True)
class RouteObservation:
    reference_token: str
    output: TensorMeta
    output_source: int  # ordinal of the distinct tensor object, to link route output to its use


@dataclass(frozen=True, slots=True)
class CfgCallObservation:
    step_index: int
    branch: CfgBranch
    clip_fea: TensorMeta
    clip_fea_source: int
    y: TensorMeta
    y_source: int
    context: TensorMeta


@dataclass(frozen=True, slots=True)
class ConditioningObservation:
    clip_route: RouteObservation
    vae_route: RouteObservation
    cfg_calls: tuple[CfgCallObservation, ...]


@dataclass(frozen=True, slots=True)
class GenerationOutput:
    """Result of one backend generation. ``video_shape`` is (channels, frames, height, width)."""

    artefact_uri: str = field(repr=False)
    video_shape: tuple[int, int, int, int]
    gpu_seconds: float | None
    observation: ConditioningObservation


class Wan21Backend(Protocol):
    """The only boundary to the upstream pipeline. Every method is lazy and side-effect free until
    called; importing a module that defines a backend must load nothing."""

    @property
    def info(self) -> BackendInfo: ...

    def check_available(self) -> None:
        """Raise :class:`BackendUnavailable` if dependencies, devices or permissions are absent."""
        ...

    def environment_sha256(self) -> str:
        """Digest of the backend's actual software environment (see compute_environment_digest)."""
        ...

    def load(self, checkpoint: VerifiedCheckpoint) -> None:
        """Load models from a checkpoint whose files were just hashed. No downloads, ever."""
        ...

    def generate(self, request: GenerationRequest, stop: StopSignal) -> GenerationOutput:
        """Generate one video, polling ``stop`` and honouring ``request.deadline_seconds``."""
        ...

    def cleanup(self) -> None:
        """Release per-attempt resources (e.g. free GPU memory). Called after every attempt."""
        ...

    def close(self) -> None:
        """Unload everything. Called when the executor is closed."""
        ...


class ConditioningContractViolation(Exception):
    """The observed conditioning does not match the baseline contract. ``problems`` are fixed."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def verify_conditioning(
    observation: ConditioningObservation, request: GenerationRequest
) -> ConditioningSummary:
    """Check the observed control flow against the baseline contract; summarise if it holds.

    * Both image routes consumed the request's one reference token.
    * Each denoising step makes a positive call then a negative call (the upstream order), with
      consecutive step indices starting at 0.
    * Both branches receive the *same* image conditioning: identical CLIP features and VAE
      first-frame condition (same tensor object and the same metadata), so guidance contrasts
      text only.
    * The CLIP features the denoiser received are the CLIP route's output, and are the same
      object at every step.
    """
    problems = []
    token = request.reference.token
    clip, vae = observation.clip_route, observation.vae_route
    if clip.reference_token != token:
        problems.append("CLIP route did not receive the request's reference")
    if vae.reference_token != token:
        problems.append("VAE first-frame route did not receive the request's reference")
    calls = observation.cfg_calls
    if not calls or len(calls) % 2:
        problems.append("expected a positive and a negative CFG call for every step")
    else:
        for position, call in enumerate(calls):
            step, expected_branch = divmod(position, 2)
            if call.step_index != step or call.branch != ("positive", "negative")[expected_branch]:
                problems.append("CFG calls are not ordered as step-wise positive then negative")
                break
        for positive, negative in zip(calls[::2], calls[1::2], strict=True):
            if (positive.clip_fea, positive.clip_fea_source) != (
                negative.clip_fea,
                negative.clip_fea_source,
            ) or (positive.y, positive.y_source) != (negative.y, negative.y_source):
                problems.append("positive and negative branches received different conditioning")
                break
        if len({(c.clip_fea_source, c.y_source) for c in calls}) > 1:
            problems.append("image conditioning changed between steps")
        if any(c.clip_fea_source != clip.output_source or c.clip_fea != clip.output for c in calls):
            problems.append("the denoiser did not receive the CLIP route's output")
    if problems:
        raise ConditioningContractViolation(problems)
    first = calls[0]
    return ConditioningSummary(
        same_reference_on_both_routes=True,
        clip_features=first.clip_fea,
        vae_first_frame_condition=first.y,
        positive_branch_calls=len(calls) // 2,
        negative_branch_calls=len(calls) // 2,
        branches_share_image_conditioning=True,
        clip_route_feeds_denoiser=True,
    )


def output_problems(output: GenerationOutput, request: GenerationRequest) -> list[str]:
    """Check the reported artefact location and video shape against the request."""
    problems = []
    if output.artefact_uri != request.output_uri:
        problems.append("artefact was not written to the requested private location")
    channels, frames, height, width = output.video_shape
    if channels != VIDEO_CHANNELS:
        problems.append("video must have 3 colour channels")
    if frames != request.frame_count:
        problems.append("video frame count differs from the frozen frame_count")
    if height * width > request.max_area:
        problems.append("video area exceeds the frozen max_area")
    if height % WAN21_SPATIAL_MULTIPLE or width % WAN21_SPATIAL_MULTIPLE:
        problems.append("video height and width must be multiples of 16")
    if min(height, width) <= 0:
        problems.append("video dimensions must be positive")
    if output.gpu_seconds is not None and not output.gpu_seconds >= 0:
        problems.append("gpu_seconds must be a non-negative number")
    return problems
