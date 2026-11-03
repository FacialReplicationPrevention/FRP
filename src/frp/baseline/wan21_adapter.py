"""Gated adapter from the baseline executor to the pinned upstream Wan 2.1 I2V pipeline.

**Not activated. No command constructs it, no test runs it against real code, and the executor in
front of it refuses everything unless a separately reviewed private authorisation provider grants
this exact live run.** Merging this module authorises nothing (see ``docs/gpu-readiness.md``).

:class:`Wan21UpstreamAdapter` implements the :class:`~frp.baseline.backend.Wan21Backend` protocol
over an injected :class:`~frp.baseline.wan21_runtime.UpstreamRuntime`. The executor keeps every
gate it already has (exact-run, authorisation, prompt-extension modules, source commit, environment
digest, per-file weight hashes, blocked network, output and conditioning checks, cleanup); the
adapter adds only what needs the upstream call:

* **Control mapping** (:func:`map_request`). Every argument of the pinned
  ``WanI2V.generate(input_prompt, img, max_area, frame_num, shift, sample_solver, sampling_steps,
  guide_scale, n_prompt, seed, offload_model)`` (``wan/image2video.py`` L133-L144) is passed
  explicitly from the frozen manifest, so no upstream default is used silently. Unsupported or
  inconsistent settings are refused, never replaced by defaults.
* **Fail-closed configuration** (:func:`configuration_problems`), checked in ``check_available`` so
  an unsupported manifest is refused before anything is loaded.
* **Conditioning instrumentation** (:mod:`frp.baseline.wan21_probe`): the same original image on
  the CLIP and VAE first-frame routes and in both CFG branches, recorded as metadata only.
* **Geometry, output and lifecycle**: exact expected output size, typed failures without
  messages, cleanup of staged files and GPU memory. ``generate`` only **stages** the video in an
  exclusive owner-only partial file of a :class:`~frp.private_storage.OutputStore`; the executor
  publishes it with :meth:`Wan21UpstreamAdapter.commit_output` only after every post-generation
  check, and :meth:`~Wan21UpstreamAdapter.discard_output` rolls a committed file back (inode
  checked) if anything later fails, so a rejected result never leaves a final or partial file.
* **Approved reference bytes**: :meth:`Wan21UpstreamAdapter.check_attempt` hashes the bounded,
  no-follow reference read against the grant's SHA-256 *before* the model is loaded; ``generate``
  re-reads and re-hashes before decoding (a mismatch there is a failure with no output).

A success through a fake runtime is **not** a Wan 2.1 inference: ``info.live`` is true only for the
real :class:`~frp.baseline.wan21_runtime.TorchWanRuntime`, so results over any other runtime are
labelled ``simulated``.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from frp.baseline.backend import (
    BackendError,
    BackendInfo,
    BackendUnavailable,
    ConditioningContractViolation,
    GenerationInterrupted,
    GenerationOutput,
    GenerationRequest,
    GenerationResourceExhausted,
    GenerationTimeout,
    ModelLoadError,
    OutputContractViolation,
    StopSignal,
    output_problems,
    verify_conditioning,
)
from frp.baseline.manifest import BaselineManifest, unset_execution_fields
from frp.baseline.preflight import (
    RemoteAccessBlocked,
    VerifiedCheckpoint,
    network_blocked,
    prohibited_modules_loaded,
)
from frp.baseline.protocol import (
    WAN21_BASELINE_RESOLUTIONS,
    WAN21_CHECKPOINT_REVISION,
    WAN21_MAX_AREA,
    WAN21_SAMPLE_SOLVERS,
    WAN21_SOURCE_COMMIT,
)
from frp.baseline.wan21_probe import ConditioningProbe
from frp.baseline.wan21_runtime import TorchWanRuntime, UpstreamConfigFacts, UpstreamRuntime
from frp.manifest import SEED_MAX, SEED_MIN
from frp.private_storage import OutputStore, ReferenceReader, Reservation, StorageError

ADAPTER_NAME: Final = "wan21-upstream-adapter"

# Upstream exposes no precision argument: dtypes are fixed by the i2v-14B config
# (wan/configs/shared_config.py L10, L14; wan_i2v_14B.py L18) and the WanVAE default
# (wan/modules/vae.py L624). This is the only ``precision`` value the adapter accepts.
WAN21_UPSTREAM_PRECISION: Final = "upstream-i2v-14B-config"

# Facts of the pinned source that the loaded pipeline must reproduce.
PINNED_UPSTREAM_CONFIG: Final = MappingProxyType(
    {
        "config_name": "Config: Wan I2V 14B",  # wan/configs/wan_i2v_14B.py L9
        "model_type": "i2v",  # checkpoint config.json at the pinned revision (Research 005)
        "sample_fps": 16,  # wan/configs/shared_config.py L18
        "vae_stride": (4, 8, 8),  # wan/configs/wan_i2v_14B.py L24
        "patch_size": (1, 2, 2),  # wan/configs/wan_i2v_14B.py L27
        "param_dtype": "torch.bfloat16",  # wan/configs/shared_config.py L14
        "t5_dtype": "torch.bfloat16",  # wan/configs/shared_config.py L10
        "clip_dtype": "torch.float16",  # wan/configs/wan_i2v_14B.py L18
        "vae_dtype": "torch.float32",  # wan/modules/vae.py L624 (WanVAE default dtype)
    }
)

# ``n_prompt=""`` makes upstream use ``config.sample_neg_prompt`` (wan/image2video.py L219-L220),
# which is the manifest's ``negative_prompt_policy: upstream_config_default``.
UPSTREAM_DEFAULT_NEGATIVE_PROMPT: Final = ""

# Files the pinned loaders open (wan/configs/wan_i2v_14B.py L13-L23; WanModel.from_pretrained),
# named as in the Hub file list at revision 6b73f84 (metadata, not locally verified).
WAN21_I2V_PICKLE_FILES: Final = (
    "Wan2.1_VAE.pth",
    "models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth",
    "models_t5_umt5-xxl-enc-bf16.pth",
)
WAN21_I2V_REQUIRED_FILES: Final = (
    *WAN21_I2V_PICKLE_FILES,
    "config.json",
    "diffusion_pytorch_model.safetensors.index.json",
    *(f"diffusion_pytorch_model-{i:05d}-of-00007.safetensors" for i in range(1, 8)),
    *(
        f"{tokenizer}/{name}"
        for tokenizer in ("google/umt5-xxl", "xlm-roberta-large")
        for name in ("special_tokens_map.json", "tokenizer.json", "tokenizer_config.json")
    ),
    "google/umt5-xxl/spiece.model",
    "xlm-roberta-large/sentencepiece.bpe.model",
)
PICKLE_SUFFIXES: Final = (".pth", ".pt", ".bin", ".pkl", ".pickle", ".ckpt")

# Latent stride 8 x patch 2 (wan/image2video.py L186-L193).
_VAE_STRIDE_HW: Final = 8
_PATCH_HW: Final = 2
_DECIDED_CONTROLS: Final = (
    ("use_prompt_extend", False),
    ("clip_conditioning", "original"),
    ("vae_first_frame_conditioning", "original"),
    ("adapters", "none"),
    ("remote_inference_services", "none"),
    ("negative_prompt_policy", "upstream_config_default"),
    ("generator", "upstream_seeded_torch_cuda_generator"),
    ("artefact_storage", "private_only"),
    ("image_count_per_identity", 1),
)


class UnsupportedConfiguration(BackendUnavailable):
    """The manifest or request asks for something the adapter does not support."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


class InvalidReference(BackendError):
    """The private reference could not be opened or does not fit the frozen controls."""


class OutputRejected(BackendError):
    """The private output location is unusable or the video could not be written."""


class UpstreamGenerationFailed(BackendError):
    """Upstream generation raised. The original exception text is never kept or recorded."""


@dataclass(frozen=True, slots=True)
class UpstreamCall:
    """Keyword arguments for the pinned ``WanI2V.generate`` (wan/image2video.py L133-L144)."""

    max_area: int
    frame_num: int
    shift: float
    sample_solver: str
    sampling_steps: int
    guide_scale: float
    n_prompt: str
    seed: int
    offload_model: bool

    def kwargs(self) -> dict[str, Any]:
        return {
            "max_area": self.max_area,
            "frame_num": self.frame_num,
            "shift": self.shift,
            "sample_solver": self.sample_solver,
            "sampling_steps": self.sampling_steps,
            "guide_scale": self.guide_scale,
            "n_prompt": self.n_prompt,
            "seed": self.seed,
            "offload_model": self.offload_model,
        }


def checkpoint_file_problems(names: Iterable[str]) -> list[str]:
    """Problems with the approved checkpoint file list (counts only, never names)."""
    names = set(names)
    problems = []
    if missing := [name for name in WAN21_I2V_REQUIRED_FILES if name not in names]:
        problems.append(f"{len(missing)} file(s) the pinned upstream loaders open are not approved")
    extra_pickles = [
        name
        for name in names
        if name.lower().endswith(PICKLE_SUFFIXES) and name not in WAN21_I2V_PICKLE_FILES
    ]
    if extra_pickles:
        problems.append(
            f"{len(extra_pickles)} pickle-format file(s) beyond the three upstream .pth files"
        )
    return problems


def configuration_problems(manifest: BaselineManifest) -> list[str]:
    """Why the adapter would refuse this manifest (fixed strings; empty means supported)."""
    problems = []
    if unset_execution_fields(manifest):
        problems.append("the manifest is not execution ready")
    if any(getattr(manifest, name) != value for name, value in _DECIDED_CONTROLS):
        problems.append("a decided baseline control differs from the only supported value")
    if (manifest.upstream_commit_sha, manifest.checkpoint_revision) != (
        WAN21_SOURCE_COMMIT,
        WAN21_CHECKPOINT_REVISION,
    ):
        problems.append("source commit or checkpoint revision is not the reviewed pin")
    if manifest.resolution is not None and manifest.resolution not in WAN21_BASELINE_RESOLUTIONS:
        problems.append("resolution is not a supported 480P size")
    if manifest.sampler is not None and manifest.sampler not in WAN21_SAMPLE_SOLVERS:
        problems.append("sampler is not an upstream sample_solver choice")
    if manifest.precision is not None and manifest.precision != WAN21_UPSTREAM_PRECISION:
        problems.append(
            f"precision must be {WAN21_UPSTREAM_PRECISION!r}: upstream has no precision argument"
        )
    if manifest.frame_count is not None and manifest.frame_count % 4 != 1:
        problems.append("frame_count must have the form 4n+1")
    if any(not SEED_MIN <= seed <= SEED_MAX for seed in manifest.seeds):
        problems.append("seeds must be non-negative (upstream draws a random seed otherwise)")
    if manifest.checkpoint_hashes is not None:
        problems.extend(checkpoint_file_problems(manifest.checkpoint_hashes))
    return problems


def config_problems(facts: UpstreamConfigFacts) -> list[str]:
    """Differences between the loaded upstream configuration and the pinned source."""
    problems = [
        f"upstream {name} differs from the pinned source"
        for name, expected in PINNED_UPSTREAM_CONFIG.items()
        if getattr(facts, name) != expected
    ]
    if not facts.negative_prompt:
        problems.append("upstream config default negative prompt is empty")
    return problems


def map_request(request: GenerationRequest, manifest: BaselineManifest) -> UpstreamCall:
    """Map one request to the upstream call; refuse anything that differs from the manifest."""
    if problems := configuration_problems(manifest):
        raise UnsupportedConfiguration(problems)
    call = UpstreamCall(
        max_area=WAN21_MAX_AREA[manifest.resolution or ""],
        frame_num=manifest.frame_count or 0,
        shift=manifest.sample_shift or 0.0,
        sample_solver=manifest.sampler or "",
        sampling_steps=manifest.sampling_steps or 0,
        guide_scale=manifest.guidance_scale or 0.0,
        n_prompt=UPSTREAM_DEFAULT_NEGATIVE_PROMPT,
        seed=request.seed,
        offload_model=manifest.offload_model is True,
    )
    pairs = (
        ("max_area", request.max_area, call.max_area),
        ("frame_count", request.frame_count, call.frame_num),
        ("sample_shift", request.sample_shift, call.shift),
        ("sample_solver", request.sample_solver, call.sample_solver),
        ("sampling_steps", request.sampling_steps, call.sampling_steps),
        ("guide_scale", request.guide_scale, call.guide_scale),
    )
    problems = [
        f"request {name} differs from the manifest" for name, got, want in pairs if got != want
    ]
    if request.offload_model is not call.offload_model:
        problems.append("request offload_model differs from the manifest")
    if request.seed not in manifest.seeds:
        problems.append("request seed is not a planned seed")
    if request.prompt_text not in {prompt.text for prompt in manifest.prompts}:
        problems.append("request prompt is not a planned prompt")
    if not (math.isfinite(request.deadline_seconds) and request.deadline_seconds > 0):
        problems.append("request deadline must be a positive number of seconds")
    if problems:
        raise UnsupportedConfiguration(problems)
    return call


@contextlib.contextmanager
def _no_remote_access() -> Iterator[None]:
    """Raise :class:`RemoteAccessBlocked` if anything inside tried the network, even if the
    upstream code caught the refusal, so no artefact is written after a blocked attempt.

    Nested inside the executor's own guard, so blocked attempts are counted here instead.
    """
    with network_blocked() as guard:
        try:
            yield
        except Exception:
            if guard.blocked_calls:
                raise RemoteAccessBlocked("network access was attempted") from None
            raise
    if guard.blocked_calls:
        raise RemoteAccessBlocked("network access was attempted")


def expected_geometry(image_height: int, image_width: int, max_area: int) -> tuple[int, int]:
    """Output (height, width) the pinned upstream derives from the reference and ``max_area``.

    Mirrors wan/image2video.py L184-L193: orientation follows the reference's aspect ratio, and
    ``max_area`` is the same for both 480P sizes, so the size label does not choose orientation.
    """
    aspect_ratio = image_height / image_width
    lat_h = round(math.sqrt(max_area * aspect_ratio) // _VAE_STRIDE_HW // _PATCH_HW * _PATCH_HW)
    lat_w = round(math.sqrt(max_area / aspect_ratio) // _VAE_STRIDE_HW // _PATCH_HW * _PATCH_HW)
    return lat_h * _VAE_STRIDE_HW, lat_w * _VAE_STRIDE_HW


def reference_geometry_problem(
    resolution: str, image_height: int, image_width: int, max_area: int
) -> str | None:
    """Refuse references whose orientation contradicts the manifest's ``width*height`` label.

    Wan size labels are ``width*height`` (``SIZE_CONFIGS`` in wan/configs/__init__.py L30-L36 and
    the ``(width,height)`` size in wan/text2video.py L131-L132).
    """
    if image_height <= 0 or image_width <= 0:
        return "the reference has no pixels"
    label_width, label_height = (int(part) for part in resolution.split("*"))
    if image_height == image_width or (image_height > image_width) != (label_height > label_width):
        return "the reference orientation does not match the manifest resolution"
    height, width = expected_geometry(image_height, image_width, max_area)
    if min(height, width) < _VAE_STRIDE_HW * _PATCH_HW:
        return "the reference aspect ratio is too extreme for the frozen max_area"
    return None


class Wan21UpstreamAdapter:
    """:class:`~frp.baseline.backend.Wan21Backend` over the pinned upstream ``WanI2V``.

    Use only through :class:`~frp.baseline.executor.Wan21BaselineExecutor`; on its own it performs
    none of the executor's authorisation, provenance or hash checks.
    """

    def __init__(
        self,
        *,
        manifest: BaselineManifest,
        runtime: UpstreamRuntime,
        artefacts: OutputStore,
        references: ReferenceReader,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._manifest = manifest
        self._runtime = runtime
        self._artefacts = artefacts
        self._references = references
        self._timer = timer
        self._pipeline: Any = None
        self._facts: UpstreamConfigFacts | None = None
        self._staged: dict[str, Reservation] = {}
        self._committed: dict[str, Reservation] = {}

    @property
    def info(self) -> BackendInfo:
        # Only the real runtime can produce a live result; any injected stand-in is simulated.
        live = type(self._runtime) is TorchWanRuntime
        return BackendInfo(name=ADAPTER_NAME, revision=WAN21_SOURCE_COMMIT, live=live)

    def check_available(self) -> None:
        if problems := configuration_problems(self._manifest):
            raise UnsupportedConfiguration(problems)
        self._runtime.check_available()

    @property
    def source_dir(self) -> Path | None:
        """The checkout upstream code is imported from; the executor requires it to be its own."""
        return getattr(self._runtime, "source_dir", None)

    def environment_sha256(self) -> str:
        return self._runtime.environment_sha256()

    # -- load ---------------------------------------------------------------------------------

    def load(self, checkpoint: VerifiedCheckpoint) -> None:
        if not isinstance(checkpoint, VerifiedCheckpoint) or self._pipeline is not None:
            raise ModelLoadError
        if configuration_problems(self._manifest):
            raise ModelLoadError
        try:
            device = self._runtime.device_name()
        except Exception:
            raise ModelLoadError from None
        if device != self._manifest.gpu_model:
            raise ModelLoadError
        pipeline: Any = None
        loaded = False
        try:
            pipeline = self._runtime.build_pipeline(checkpoint)
            facts = self._runtime.config_facts(pipeline)
            if config_problems(facts):
                raise ModelLoadError
            self._pipeline, self._facts = pipeline, facts
            loaded = True
        except (ModelLoadError, GenerationResourceExhausted, RemoteAccessBlocked):
            raise
        except Exception as exc:
            if self._runtime.is_out_of_memory(exc):
                raise GenerationResourceExhausted from None
            raise ModelLoadError from None
        finally:
            if not loaded:
                pipeline = None
                with contextlib.suppress(Exception):
                    self._runtime.release_memory()

    # -- generate -----------------------------------------------------------------------------

    def check_attempt(self, request: GenerationRequest) -> None:
        """Before any model load: the store is sound, the output is reservable, the reference is
        exactly the approved bytes. Bounded and hash-only: nothing is decoded or written."""
        if problems := configuration_problems(self._manifest):
            raise UnsupportedConfiguration(problems)
        try:
            if self._artefacts.problems() or self._references.problems():
                raise OutputRejected
            self._artefacts.check_reservable(request.output_uri)
        except StorageError:
            raise OutputRejected from None
        self._read_approved_reference(request)

    def _read_approved_reference(self, request: GenerationRequest) -> bytes:
        try:
            data = self._references.read(request.reference.location)
        except (StorageError, OSError):
            raise InvalidReference from None
        if hashlib.sha256(data).hexdigest() != request.reference_sha256:
            raise InvalidReference
        return data

    def generate(self, request: GenerationRequest, stop: StopSignal) -> GenerationOutput:
        pipeline, facts = self._pipeline, self._facts
        if pipeline is None or facts is None:
            raise UpstreamGenerationFailed
        call = map_request(request, self._manifest)
        started = self._timer()

        def checkpoint() -> None:
            if (reason := stop.reason()) is not None:
                raise GenerationInterrupted(reason)
            if self._timer() - started > request.deadline_seconds:
                raise GenerationTimeout

        checkpoint()
        reservation = self._reserve_output(request.output_uri)
        probe: ConditioningProbe | None = None
        staged = False
        try:
            image, reference, geometry = self._open_reference(request, call.max_area)
            checkpoint()
            probe = ConditioningProbe(
                inspector=self._runtime,
                reference=reference,
                reference_token=request.reference.token,
                prompt_text=request.prompt_text,
                negative_prompt=facts.negative_prompt,
                frame_count=call.frame_num,
                before_denoiser_call=checkpoint,
            )
            probe.install(pipeline)
            upstream_started = self._timer()
            try:
                with _no_remote_access():
                    video = self._call_upstream(pipeline, request.prompt_text, image, call)
            finally:
                probe.restore()
            # Wall-clock seconds of the upstream call on the device (not a utilisation figure).
            upstream_seconds = max(0.0, self._timer() - upstream_started)
            del image, reference
            observation = probe.observation()
            output = GenerationOutput(
                artefact_uri=request.output_uri,
                video_shape=self._video_shape(video),
                gpu_seconds=upstream_seconds,
                observation=observation,
            )
            if output_problems(output, request) or output.video_shape[2:] != geometry:
                raise OutputContractViolation
            verify_conditioning(observation, request)  # never write a video that fails it
            if prohibited_modules_loaded():
                raise UpstreamGenerationFailed  # the executor records prohibited_module_loaded
            checkpoint()
            with _no_remote_access():
                self._runtime.save_video(video, reservation.partial_path, facts.sample_fps)
            del video
            # Staged only: the executor commits after its own post-generation checks.
            self._staged[request.output_uri] = reservation
            staged = True
            return output
        except OSError:
            raise OutputRejected from None
        finally:
            if probe is not None:
                probe.release()
            if not staged:
                self._discard_reservation(reservation)

    def _reserve_output(self, artefact_uri: str) -> Reservation:
        """Exclusive owner-only partial plus a ledger marker; a spent attempt is never reused."""
        if artefact_uri in self._staged or artefact_uri in self._committed:
            raise OutputRejected
        try:
            return self._artefacts.reserve(artefact_uri)
        except StorageError:
            raise OutputRejected from None

    def _open_reference(
        self, request: GenerationRequest, max_area: int
    ) -> tuple[Any, Any, tuple[int, int]]:
        data = self._read_approved_reference(request)  # re-verified: the file may have changed
        try:
            image = self._runtime.decode_reference(data)
            height, width = self._runtime.image_size(image)
        except MemoryError:
            raise GenerationResourceExhausted from None
        except Exception:
            raise InvalidReference from None
        resolution = self._manifest.resolution or ""
        if reference_geometry_problem(resolution, height, width, max_area):
            raise InvalidReference
        try:
            reference = self._runtime.reference_tensor(image)
        except Exception:
            raise InvalidReference from None
        return image, reference, expected_geometry(height, width, max_area)

    # -- commit and rollback --------------------------------------------------------------------

    def commit_output(self, request: GenerationRequest) -> None:
        """Publish the staged output (identity-checked, no-replace); on failure nothing stays."""
        reservation = self._staged.get(request.output_uri)
        if reservation is None:
            raise OutputRejected
        try:
            self._artefacts.commit(reservation)
        except BaseException:
            self._staged.pop(request.output_uri, None)
            self._rollback(reservation)
            raise
        self._staged.pop(request.output_uri, None)
        self._committed[request.output_uri] = reservation

    def discard_output(self, request: GenerationRequest) -> None:
        """Roll a committed output back (only the file this adapter committed). Idempotent."""
        reservation = self._committed.pop(request.output_uri, None)
        if reservation is not None:
            self._rollback(reservation)
        staged = self._staged.pop(request.output_uri, None)
        if staged is not None:
            self._discard_reservation(staged)

    def _rollback(self, reservation: Reservation) -> None:
        with contextlib.suppress(StorageError):
            self._artefacts.rollback(reservation)
        self._discard_reservation(reservation)

    def _discard_reservation(self, reservation: Reservation) -> None:
        with contextlib.suppress(StorageError):
            self._artefacts.discard(reservation)

    def _call_upstream(self, pipeline: Any, prompt: str, image: Any, call: UpstreamCall) -> Any:
        try:
            return pipeline.generate(prompt, image, **call.kwargs())
        except (
            GenerationInterrupted,
            GenerationTimeout,
            GenerationResourceExhausted,
            ConditioningContractViolation,
            RemoteAccessBlocked,
        ):
            raise
        except Exception as exc:
            if self._runtime.is_out_of_memory(exc):
                raise GenerationResourceExhausted from None
            raise UpstreamGenerationFailed from None

    def _video_shape(self, video: Any) -> tuple[int, int, int, int]:
        try:
            shape = self._runtime.tensor_meta(video).shape
        except Exception:
            raise OutputContractViolation from None
        if len(shape) != 4:
            raise OutputContractViolation
        return shape[0], shape[1], shape[2], shape[3]

    # -- cleanup ------------------------------------------------------------------------------

    def cleanup(self) -> None:
        """Discard any staged (uncommitted) output and free GPU memory; committed files stay."""
        leftover = False
        for uri, reservation in list(self._staged.items()):
            self._discard_reservation(reservation)
            del self._staged[uri]
        try:
            self._runtime.release_memory()
        except Exception:
            leftover = True
        if leftover:
            raise BackendError("cleanup incomplete")

    def close(self) -> None:
        self._pipeline = None
        self._facts = None
        with contextlib.suppress(Exception):
            self._runtime.release_memory()


__all__ = [
    "ADAPTER_NAME",
    "PINNED_UPSTREAM_CONFIG",
    "UPSTREAM_DEFAULT_NEGATIVE_PROMPT",
    "WAN21_I2V_PICKLE_FILES",
    "WAN21_I2V_REQUIRED_FILES",
    "WAN21_UPSTREAM_PRECISION",
    "InvalidReference",
    "OutputRejected",
    "UnsupportedConfiguration",
    "UpstreamCall",
    "UpstreamGenerationFailed",
    "Wan21UpstreamAdapter",
    "checkpoint_file_problems",
    "config_problems",
    "configuration_problems",
    "expected_geometry",
    "map_request",
    "reference_geometry_problem",
]
