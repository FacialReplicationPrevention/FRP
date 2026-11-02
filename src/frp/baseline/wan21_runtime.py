"""Real upstream runtime for the gated Wan 2.1 adapter. **Constructed by no command; never run.**

:class:`TorchWanRuntime` is the only code in this repository that would import ``torch``,
``torchvision``, ``PIL`` or the upstream ``wan`` package, and it does so **only inside its
methods**: importing this module imports none of them. It has never been executed against a GPU,
real weights or a real image, so every statement below about runtime behaviour is a reading of the
pinned source, not an observation.

Source facts this runtime relies on (Wan-Video/Wan2.1 ``9737cba9c1c3c4d04b33fcad41c111989865d315``):

* ``wan.WanI2V(config, checkpoint_dir, device_id, rank, t5_fsdp, dit_fsdp, use_usp, t5_cpu,
  init_on_cpu)`` builds T5, VAE and CLIP from ``.pth`` files under ``checkpoint_dir`` and the DiT
  with ``WanModel.from_pretrained(checkpoint_dir)`` (``wan/image2video.py`` L34-L131).
* The three ``.pth`` loaders call ``torch.load`` **without** ``weights_only``
  (``wan/modules/t5.py`` L496, ``vae.py`` L614, ``clip.py`` L519). Only torch >= 2.6 defaults to
  restricted (weights-only) unpickling, and ``TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`` turns that off, so
  :meth:`TorchWanRuntime.check_available` requires torch >= 2.6 and refuses that variable. Whether
  the pinned ``.pth`` files load under weights-only unpickling is **unverified**; if they do not,
  loading fails closed (``model_load_error``) and there is deliberately no unsafe fallback.
* Importing ``wan`` calls ``torch.cuda.current_device()`` at import (default argument at
  ``wan/modules/t5.py`` L478) and sets ``TOKENIZERS_PARALLELISM`` (``wan/configs/__init__.py``
  L5), so ``wan`` is imported only inside :meth:`build_pipeline`, which the executor calls with
  network access blocked. ``wan/__init__.py`` does not import ``wan.utils.prompt_extend``; the
  upstream ``generate.py`` does (L19) and is never imported.
* The tokenizers are read with ``AutoTokenizer.from_pretrained(<checkpoint_dir>/<name>)``
  (``wan/modules/tokenizers.py`` L46), so ``HF_HUB_OFFLINE=1`` and ``TRANSFORMERS_OFFLINE=1`` are
  required: a missing local file must fail rather than fall back to a hub download.
* Upstream ``cache_video`` prints its exception text on failure (``wan/utils/utils.py`` L60), which
  could contain a path, so its standard output is discarded.
"""

from __future__ import annotations

import contextlib
import gc
import importlib
import importlib.metadata
import importlib.util
import io
import logging
import os
import platform
import re
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

from frp.baseline.backend import BackendUnavailable
from frp.baseline.preflight import (
    VerifiedCheckpoint,
    compute_environment_digest,
    prohibited_modules_loaded,
)
from frp.baseline.results import TensorMeta
from frp.baseline.wan21_probe import TensorInspector

UPSTREAM_TASK: Final = "i2v-14B"
REQUIRED_MODULES: Final = (
    "torch",
    "torchvision",
    "PIL",
    "numpy",
    "diffusers",
    "transformers",
    "tokenizers",
    "easydict",
    "ftfy",
    "regex",
    "einops",
    "imageio",
    "imageio_ffmpeg",
    "tqdm",
)
MIN_TORCH_VERSION: Final = (2, 6)
REQUIRED_OFFLINE_VARIABLES: Final = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
UNSAFE_LOAD_VARIABLES: Final = ("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD",)
# Continuous integration and Codespaces are never execution environments for this runtime.
REFUSED_ENVIRONMENT_VARIABLES: Final = ("CI", "GITHUB_ACTIONS", "CODESPACES", "CODESPACE_NAME")
# ``msk`` contributes 4 channels ahead of the VAE latent (wan/image2video.py L210-L217, L249).
MASK_CHANNELS: Final = 4
_WAN_MODULES: Final = ("wan", "wan.configs", "wan.utils.utils")


class RuntimeUnavailable(BackendUnavailable):
    """The runtime cannot be used here. ``problems`` are fixed strings without values or paths."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True, slots=True)
class UpstreamConfigFacts:
    """Values read from the loaded upstream pipeline, compared with the pinned source at load."""

    config_name: str
    model_type: str
    sample_fps: int
    vae_stride: tuple[int, ...]
    patch_size: tuple[int, ...]
    param_dtype: str
    t5_dtype: str
    clip_dtype: str
    vae_dtype: str
    negative_prompt: str = field(repr=False)


class UpstreamRuntime(TensorInspector, Protocol):
    """The narrow upstream surface the adapter uses; CPU tests inject a fake."""

    def check_available(self) -> None:
        """Raise :class:`BackendUnavailable` without importing any ML package."""
        ...

    def environment_sha256(self) -> str: ...

    def device_name(self) -> str: ...

    def build_pipeline(self, checkpoint: VerifiedCheckpoint) -> Any: ...

    def config_facts(self, pipeline: Any) -> UpstreamConfigFacts: ...

    def open_reference(self, location: str) -> Any: ...

    def image_size(self, image: Any) -> tuple[int, int]:
        """(height, width) of the opened reference."""
        ...

    def reference_tensor(self, image: Any) -> Any: ...

    def is_out_of_memory(self, error: BaseException) -> bool: ...

    def save_video(self, video: Any, path: Path, fps: int) -> None: ...

    def release_memory(self) -> None: ...


def torch_version_problem(version: str | None) -> str | None:
    match = re.match(r"^(\d+)\.(\d+)", version or "")
    if match is None:
        return "the installed torch version could not be determined"
    if (int(match[1]), int(match[2])) < MIN_TORCH_VERSION:
        return "torch older than 2.6 unpickles .pth checkpoints without weights-only restrictions"
    return None


def runtime_environment_problems(environ: Mapping[str, str]) -> list[str]:
    """Fixed descriptions (variable names only, never values) of a refused environment."""
    problems = []
    if any(environ.get(name) for name in REFUSED_ENVIRONMENT_VARIABLES):
        problems.append("CI and Codespaces are never permitted execution environments")
    if missing := [name for name in REQUIRED_OFFLINE_VARIABLES if environ.get(name) != "1"]:
        problems.append(f"{', '.join(missing)} must be 1 so no hub download can be attempted")
    if any(environ.get(name) for name in UNSAFE_LOAD_VARIABLES):
        problems.append("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD must be unset (it disables safe loading)")
    return problems


def _within(module: Any, root: Path) -> bool:
    location = getattr(module, "__file__", None)
    return location is not None and Path(location).resolve().is_relative_to(root)


@contextlib.contextmanager
def _without_info_logging() -> Iterator[None]:
    """Upstream logs checkpoint paths at INFO while loading (e.g. ``clip.py`` L517)."""
    previous = logging.root.manager.disable
    logging.disable(max(previous, logging.INFO))
    try:
        yield
    finally:
        logging.disable(previous)


class TorchWanRuntime:
    """Pinned-upstream implementation of :class:`UpstreamRuntime`. Never constructed in CI.

    ``source_dir`` must be the same clean checkout the executor verifies; ``wan`` is imported only
    from there. Construction does nothing; every import happens inside a method.
    """

    def __init__(
        self,
        *,
        source_dir: Path,
        device_id: int = 0,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._source_dir = source_dir
        self._device_id = device_id
        self._environ = os.environ if environ is None else environ

    # -- availability and provenance ---------------------------------------------------------

    def check_available(self) -> None:
        problems = runtime_environment_problems(self._environ)
        if missing := [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]:
            problems.append(f"{len(missing)} required upstream dependency module(s) are missing")
        try:
            torch_version: str | None = importlib.metadata.version("torch")
        except importlib.metadata.PackageNotFoundError:
            torch_version = None
        if problem := torch_version_problem(torch_version):
            problems.append(problem)
        if not (self._source_dir / "wan" / "image2video.py").is_file():
            problems.append("the source checkout does not contain the upstream wan package")
        existing = sys.modules.get("wan")
        if existing is not None and not _within(existing, self._source_dir.resolve()):
            problems.append("a wan package from another location is already imported")
        if problems:
            raise RuntimeUnavailable(problems)

    def environment_sha256(self) -> str:
        """Digest of installed distributions and the Python version (CUDA driver not included).

        A name installed in several locations contributes all its versions, sorted.
        """
        versions: dict[str, set[str]] = {}
        for distribution in importlib.metadata.distributions():
            name = (distribution.metadata["Name"] or "").lower()
            if name:
                versions.setdefault(name, set()).add(distribution.version)
        return compute_environment_digest(
            {name: ",".join(sorted(found)) for name, found in versions.items()},
            python_version=platform.python_version(),
            cuda_version=None,
        )

    def device_name(self) -> str:
        torch = importlib.import_module("torch")
        if not torch.cuda.is_available():
            raise RuntimeUnavailable(["no CUDA device is available"])
        return str(torch.cuda.get_device_name(self._device_id))

    # -- model lifecycle ---------------------------------------------------------------------

    def _import_wan(self) -> Any:
        source = self._source_dir.resolve()
        sys.path.insert(0, str(source))
        try:
            for name in _WAN_MODULES:
                importlib.import_module(name)
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(str(source))
        if not all(_within(sys.modules.get(name), source) for name in _WAN_MODULES):
            raise RuntimeUnavailable(["the wan package was not imported from the source checkout"])
        if prohibited_modules_loaded():
            raise RuntimeUnavailable(["a prompt-extension or remote-service module was imported"])
        return sys.modules["wan"]

    def build_pipeline(self, checkpoint: VerifiedCheckpoint) -> Any:
        wan = self._import_wan()
        config = sys.modules["wan.configs"].WAN_CONFIGS[UPSTREAM_TASK]
        with _without_info_logging():
            return wan.WanI2V(
                config=config,
                checkpoint_dir=str(checkpoint.root),
                device_id=self._device_id,
                rank=0,
                t5_fsdp=False,
                dit_fsdp=False,
                use_usp=False,
                t5_cpu=False,
                init_on_cpu=True,
            )

    def config_facts(self, pipeline: Any) -> UpstreamConfigFacts:
        config = pipeline.config
        return UpstreamConfigFacts(
            config_name=str(config.__name__),
            model_type=str(pipeline.model.model_type),
            sample_fps=int(config.sample_fps),
            vae_stride=tuple(int(v) for v in config.vae_stride),
            patch_size=tuple(int(v) for v in config.patch_size),
            param_dtype=str(config.param_dtype),
            t5_dtype=str(config.t5_dtype),
            clip_dtype=str(config.clip_dtype),
            vae_dtype=str(pipeline.vae.dtype),
            negative_prompt=str(pipeline.sample_neg_prompt),
        )

    def release_memory(self) -> None:
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def is_out_of_memory(self, error: BaseException) -> bool:
        torch = sys.modules.get("torch")
        oom = getattr(getattr(torch, "cuda", None), "OutOfMemoryError", None)
        return isinstance(error, MemoryError) or (oom is not None and isinstance(error, oom))

    # -- reference and output ----------------------------------------------------------------

    def open_reference(self, location: str) -> Any:
        image_module = importlib.import_module("PIL.Image")
        with image_module.open(location) as image:  # generate.py L392: Image.open(...).convert
            return image.convert("RGB")

    def image_size(self, image: Any) -> tuple[int, int]:
        return int(image.height), int(image.width)

    def reference_tensor(self, image: Any) -> Any:
        # The CPU part of wan/image2video.py L181, before ``.to(self.device)``.
        functional = importlib.import_module("torchvision.transforms.functional")
        return functional.to_tensor(image).sub_(0.5).div_(0.5)

    def save_video(self, video: Any, path: Path, fps: int) -> None:
        utils = sys.modules["wan.utils.utils"]
        with contextlib.redirect_stdout(io.StringIO()):
            saved = utils.cache_video(  # as generate.py L575-L581
                tensor=video[None],
                save_file=str(path),
                fps=fps,
                nrow=1,
                normalize=True,
                value_range=(-1, 1),
            )
        if saved is None:
            raise OSError("the video could not be written")

    # -- tensor inspection (metadata and equality only) --------------------------------------

    def tensor_meta(self, tensor: Any) -> TensorMeta:
        return TensorMeta(
            shape=tuple(int(d) for d in tensor.shape),
            dtype=str(tensor.dtype).removeprefix("torch."),
            device=str(tensor.device),
        )

    def clip_input_matches(self, clip_input: Any, reference: Any) -> bool:
        torch = importlib.import_module("torch")
        return (
            clip_input.dim() == 4
            and clip_input.shape[1] == 1
            and torch.equal(clip_input[:, 0], reference.to(clip_input.device))
        )

    def vae_input_matches(self, vae_input: Any, reference: Any, frame_count: int) -> bool:
        torch = importlib.import_module("torch")
        functional = importlib.import_module("torch.nn.functional")
        if vae_input.dim() != 4 or vae_input.shape[0] != 3 or vae_input.shape[1] != frame_count:
            return False
        size = (int(vae_input.shape[2]), int(vae_input.shape[3]))
        # Same CPU bicubic resize as wan/image2video.py L241-L244.
        first = functional.interpolate(reference[None].cpu(), size=size, mode="bicubic")
        return torch.equal(
            vae_input[:, :1], first.transpose(0, 1).to(vae_input.device)
        ) and not bool(vae_input[:, 1:].any())

    def vae_condition_matches(self, condition: Any, encoded: Any) -> bool:
        torch = importlib.import_module("torch")
        return (
            condition.dim() == encoded.dim()
            and condition.shape[0] == encoded.shape[0] + MASK_CHANNELS
            and tuple(condition.shape[1:]) == tuple(encoded.shape[1:])
            and torch.equal(condition[MASK_CHANNELS:], encoded)
        )


__all__ = [
    "MASK_CHANNELS",
    "UPSTREAM_TASK",
    "RuntimeUnavailable",
    "TorchWanRuntime",
    "UpstreamConfigFacts",
    "UpstreamRuntime",
    "runtime_environment_problems",
    "torch_version_problem",
]
