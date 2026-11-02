"""Synthetic, non-person stand-ins for the pinned upstream Wan 2.1 I2V interface.

Nothing here imports torch, opens an image, holds a weight or produces a video. A
:class:`FakeTensor` carries only shape/dtype/device and an opaque synthetic provenance tag, so the
fake runtime can answer the probe's equality questions. :class:`FakeWanI2V.generate` follows the
call order of the pinned ``wan/image2video.py`` (text encoder twice, CLIP once, VAE once, then
``model(**arg_c)`` and ``model(**arg_null)`` per step) so the adapter's wiring can be exercised;
passing these tests says nothing about the real model.
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
import socket
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from frp.baseline.manifest import BaselineManifest
from frp.baseline.preflight import VerifiedCheckpoint, sha256_of_file
from frp.baseline.results import TensorMeta
from frp.baseline.wan21_adapter import WAN21_I2V_REQUIRED_FILES, WAN21_UPSTREAM_PRECISION
from frp.baseline.wan21_runtime import RuntimeUnavailable, UpstreamConfigFacts
from tests.baseline_support import ARTEFACT_BASE, ENV_SHA, ready_manifest

GPU = "synthetic-gpu"
NEGATIVE_PROMPT = "synthetic config default negative prompt"
PORTRAIT = (1000, 600)  # (height, width): matches the manifest's 480*832 (width*height) label
# Keyword arguments of WanI2V.generate at the pinned commit (wan/image2video.py L133-L144).
UPSTREAM_GENERATE_KEYWORDS = (
    "max_area",
    "frame_num",
    "shift",
    "sample_solver",
    "sampling_steps",
    "guide_scale",
    "n_prompt",
    "seed",
    "offload_model",
)


@dataclass(eq=False)
class FakeTensor:
    shape: tuple[int, ...]
    dtype: str = "float32"
    device: str = "cuda:0"
    tag: tuple[Any, ...] = ()
    base: Any = None  # for a concatenated VAE condition: the encoding it contains


@dataclass(frozen=True)
class FakeImage:
    """A synthetic reference: dimensions and an opaque id, no pixels."""

    height: int
    width: int
    content: str = "synthetic-reference-0001"


class FakeOOM(RuntimeError):
    pass


class _Module:
    def to(self, *_: Any) -> _Module:
        return self

    def cpu(self) -> _Module:
        return self


class FakeTextEncoder:
    def __init__(self) -> None:
        self.model = _Module()
        self.calls: list[list[str]] = []

    def __call__(self, texts: list[str], device: Any) -> list[FakeTensor]:
        self.calls.append(list(texts))
        return [FakeTensor((7, 4096), dtype="bfloat16", tag=("text", len(self.calls)))]


class FakeClip:
    def __init__(self) -> None:
        self.model = _Module()
        self.inputs: list[Any] = []

    def visual(self, videos: list[FakeTensor]) -> FakeTensor:
        self.inputs.append(videos)
        return FakeTensor((1, 257, 1280), dtype="float16", tag=("clip",))


class FakeVae:
    dtype = "torch.float32"

    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def encode(self, videos: list[FakeTensor]) -> list[FakeTensor]:
        self.inputs.append(videos)
        _, frames, height, width = videos[0].shape
        return [FakeTensor((16, (frames - 1) // 4 + 1, height // 8, width // 8), tag=("latent",))]


class FakeDenoiser:
    model_type = "i2v"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, x: list[FakeTensor], t: Any, **kwargs: Any) -> list[FakeTensor]:
        self.calls.append(kwargs)
        return [FakeTensor(x[0].shape, tag=("prediction",))]

    def to(self, *_: Any) -> FakeDenoiser:
        return self

    def cpu(self) -> FakeDenoiser:
        return self


class FakeWanI2V:
    """Mirrors the pinned ``WanI2V.generate`` call order. ``mode`` injects one deviation."""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.text_encoder = FakeTextEncoder()
        self.clip = FakeClip()
        self.vae = FakeVae()
        self.model = FakeDenoiser()
        self.sample_neg_prompt = NEGATIVE_PROMPT
        self.generate_calls: list[dict[str, Any]] = []

    def components(self) -> tuple[Any, ...]:
        return (self.text_encoder, self.clip, self.vae, self.model)

    def generate(
        self,
        input_prompt: str,
        img: FakeImage,
        max_area: int = 720 * 1280,
        frame_num: int = 81,
        shift: float = 5.0,
        sample_solver: str = "unipc",
        sampling_steps: int = 40,
        guide_scale: float = 5.0,
        n_prompt: str = "",
        seed: int = -1,
        offload_model: bool = True,
    ) -> FakeTensor:
        mode = self.mode
        self.generate_calls.append(
            {
                "input_prompt": input_prompt,
                "img": img,
                "max_area": max_area,
                "frame_num": frame_num,
                "shift": shift,
                "sample_solver": sample_solver,
                "sampling_steps": sampling_steps,
                "guide_scale": guide_scale,
                "n_prompt": n_prompt,
                "seed": seed,
                "offload_model": offload_model,
            }
        )
        if mode == "error":
            raise RuntimeError("secret-prompt-text and /private/secret/path")
        if mode == "oom":
            raise FakeOOM("secret-oom-detail")
        if mode == "keyboard":
            raise KeyboardInterrupt
        aspect = img.height / img.width
        lat_h = round(math.sqrt(max_area * aspect) // 8 // 2 * 2)
        lat_w = round(math.sqrt(max_area / aspect) // 8 // 2 * 2)
        h, w = lat_h * 8, lat_w * 8
        n_prompt = self.sample_neg_prompt if n_prompt == "" else n_prompt
        if mode == "custom_negative":
            n_prompt = "synthetic other negative prompt"
        prompt = "synthetic other prompt" if mode == "other_prompt" else input_prompt
        context = self.text_encoder([prompt], "cuda:0")
        context_null = self.text_encoder([n_prompt], "cuda:0")
        if mode == "extra_text_call":
            self.text_encoder(["synthetic"], "cuda:0")
        clip_content = "synthetic-other-image" if mode == "clip_other_image" else img.content
        clip_input = FakeTensor((3, 1, img.height, img.width), tag=("img", clip_content))
        clip_context = self.clip.visual([clip_input])
        if mode == "clip_twice":
            self.clip.visual([clip_input])
        vae_content = "synthetic-other-image" if mode == "vae_other_image" else img.content
        tail = "nonzero" if mode == "vae_nonzero_tail" else "zeros"
        vae_input = FakeTensor((3, frame_num, h, w), tag=("vae_in", vae_content, tail))
        encoded = self.vae.encode([vae_input])[0]
        latent_frames = (frame_num - 1) // 4 + 1
        y = FakeTensor((20, latent_frames, lat_h, lat_w), tag=("condition",), base=encoded)
        other_y = FakeTensor((20, latent_frames, lat_h, lat_w), tag=("condition",))
        if mode == "y_not_from_vae":
            y = other_y
        arg_c = {"context": [context[0]], "clip_fea": clip_context, "seq_len": 1, "y": [y]}
        arg_null = {"context": context_null, "clip_fea": clip_context, "seq_len": 1, "y": [y]}
        if mode == "negative_other_y":
            arg_null["y"] = [other_y]
        if mode == "negative_other_clip":
            arg_null["clip_fea"] = FakeTensor((1, 257, 1280), dtype="float16")
        if mode == "missing_clip":
            del arg_c["clip_fea"]
        if mode == "unknown_context":
            arg_null["context"] = [FakeTensor((7, 4096), dtype="bfloat16")]
        if mode == "swap_branches":
            arg_c, arg_null = arg_null, arg_c
        if mode == "remote_call":
            socket.getaddrinfo("example.invalid", 443)
        if mode == "swallowed_remote_call":  # models upstream code that hides the refusal
            with contextlib.suppress(Exception):
                socket.getaddrinfo("example.invalid", 443)
        if mode == "dashscope":
            sys.modules["dashscope"] = types.ModuleType("dashscope")
        latent = FakeTensor((16, latent_frames, lat_h, lat_w))
        steps = sampling_steps + (1 if mode == "extra_step" else 0)
        for t in range(steps):
            self.model([latent], t=t, **arg_c)
            if mode != "skip_negative":
                self.model([latent], t=t, **arg_null)
        frames = frame_num + 4 if mode == "wrong_frames" else frame_num
        channels = 4 if mode == "wrong_channels" else 3
        height = h + 16 if mode == "wrong_geometry" else h
        return FakeTensor((channels, frames, height, w), tag=("video",))


PINNED_FACTS = UpstreamConfigFacts(
    config_name="Config: Wan I2V 14B",
    model_type="i2v",
    sample_fps=16,
    vae_stride=(4, 8, 8),
    patch_size=(1, 2, 2),
    param_dtype="torch.bfloat16",
    t5_dtype="torch.bfloat16",
    clip_dtype="torch.float16",
    vae_dtype="torch.float32",
    negative_prompt=NEGATIVE_PROMPT,
)


@dataclass
class FakeRuntime:
    """Records every call. ``mode`` injects runtime failures; ``pipeline_mode`` upstream ones."""

    mode: str = "ok"
    pipeline_mode: str = "ok"
    device: str = GPU
    env_sha: str = ENV_SHA
    image: FakeImage = field(default_factory=lambda: FakeImage(*PORTRAIT))
    facts: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    pipelines: list[FakeWanI2V] = field(default_factory=list)
    loaded_from: list[VerifiedCheckpoint] = field(default_factory=list)
    saved_fps: list[int] = field(default_factory=list)
    source_dir: Path | None = None  # None: declares no checkout (a mock needs none)

    def check_available(self) -> None:
        self.events.append("check_available")
        if self.mode == "unavailable":
            raise RuntimeUnavailable(["synthetic missing dependency"])

    def environment_sha256(self) -> str:
        self.events.append("environment")
        return self.env_sha

    def device_name(self) -> str:
        self.events.append("device_name")
        return self.device

    def build_pipeline(self, checkpoint: VerifiedCheckpoint) -> FakeWanI2V:
        self.events.append("build")
        self.loaded_from.append(checkpoint)
        if self.mode == "load_error":
            raise RuntimeError("secret /private/weights/path")
        if self.mode == "load_oom":
            raise FakeOOM("secret")
        pipeline = FakeWanI2V(self.pipeline_mode)
        self.pipelines.append(pipeline)
        return pipeline

    def config_facts(self, pipeline: FakeWanI2V) -> UpstreamConfigFacts:
        overrides = {"negative_prompt": pipeline.sample_neg_prompt, **self.facts}
        return dataclasses.replace(PINNED_FACTS, **overrides)

    def open_reference(self, location: str) -> FakeImage:
        self.events.append("open_reference")
        if self.mode == "unreadable":
            raise OSError(f"secret cannot open {location}")
        return self.image

    def image_size(self, image: FakeImage) -> tuple[int, int]:
        return image.height, image.width

    def reference_tensor(self, image: FakeImage) -> FakeTensor:
        return FakeTensor((3, image.height, image.width), device="cpu", tag=("img", image.content))

    def is_out_of_memory(self, error: BaseException) -> bool:
        return isinstance(error, FakeOOM)

    def save_video(self, video: FakeTensor, path: Path, fps: int) -> None:
        self.events.append("save")
        self.saved_fps.append(fps)
        if self.mode == "save_error":
            raise OSError("secret disk path")
        path.write_bytes(b"synthetic placeholder - not a video")

    def release_memory(self) -> None:
        self.events.append("release")
        if self.mode == "release_error":
            raise RuntimeError("secret")

    def tensor_meta(self, tensor: FakeTensor) -> TensorMeta:
        return TensorMeta(shape=tensor.shape, dtype=tensor.dtype, device=tensor.device)

    def clip_input_matches(self, clip_input: FakeTensor, reference: FakeTensor) -> bool:
        return clip_input.shape == (3, 1, *reference.shape[1:]) and clip_input.tag == reference.tag

    def vae_input_matches(self, vae_input: FakeTensor, reference: FakeTensor, frames: int) -> bool:
        return vae_input.shape[:2] == (3, frames) and vae_input.tag == (
            "vae_in",
            reference.tag[1],
            "zeros",
        )

    def vae_condition_matches(self, condition: FakeTensor, encoded: FakeTensor) -> bool:
        return condition.base is encoded


class StoreLocator:
    """Maps the synthetic private URIs onto a temporary directory (outside the repository)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def local_path(self, artefact_uri: str) -> Path:
        prefix = ARTEFACT_BASE + "/"
        if not artefact_uri.startswith(prefix):
            raise ValueError("not a synthetic store URI")
        return self.root / artefact_uri[len(prefix) :]


def make_wan_checkpoint(root: Path) -> dict[str, str]:
    """Write tiny synthetic files under the pinned upstream file names; none is a real weight."""
    for name in (*WAN21_I2V_REQUIRED_FILES, "README.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic placeholder for {name}".encode())
    return {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def adapter_manifest(expected_files: dict[str, str], **overrides: Any) -> BaselineManifest:
    values: dict[str, Any] = {"precision": WAN21_UPSTREAM_PRECISION, "gpu_model": GPU}
    values.update(overrides)
    return ready_manifest(expected_files, **values)
