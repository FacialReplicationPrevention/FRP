"""Metadata-only instrumentation of one pinned upstream ``WanI2V.generate`` call.

The pinned upstream code (Wan-Video/Wan2.1 ``9737cba9c1c3c4d04b33fcad41c111989865d315``) has no
hook for the observations in :mod:`frp.baseline.backend`. :class:`ConditioningProbe` therefore
swaps four attributes of one ``WanI2V`` instance for delegating proxies for the duration of a
single ``generate`` call and restores them afterwards. The upstream source files are not modified,
so the executor's clean-checkout check still holds. What each proxy intercepts, at the pinned
commit (``wan/image2video.py``):

* ``text_encoder`` — called once with ``[input_prompt]`` then once with ``[n_prompt]`` (L225-L226).
  The returned tensors identify the positive and negative classifier-free-guidance branches.
* ``clip`` — ``visual([img[:, None, :, :]])`` (L236): the CLIP-vision route.
* ``vae`` — ``encode([first frame + F-1 zero frames])`` (L240-L248): the VAE first-frame route;
  ``y = torch.concat([msk, y])`` (L249) then prepends 4 mask channels.
* ``model`` — the denoiser, called with ``**arg_c`` then ``**arg_null`` at every step
  (L284-L296, L308-L316).

Checks are made by the injected :class:`TensorInspector` (value equality against the reference the
adapter opened, never recorded) and by object identity. A violation raises
:class:`~frp.baseline.backend.ConditioningContractViolation` immediately, aborting the upstream
call so no further GPU time is spent. Only shape/dtype/device metadata and branch order are kept;
problem strings are fixed and never contain prompts, paths, tokens or tensor values.

These checks have run only against CPU fakes. Whether the real tensors satisfy them (for example
whether CPU bicubic resizing is bit-reproducible between the adapter and upstream) is
**unverified** until an authorised run.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Final, Protocol

from frp.baseline.backend import (
    CfgBranch,
    CfgCallObservation,
    ConditioningContractViolation,
    ConditioningObservation,
    RouteObservation,
)
from frp.baseline.results import TensorMeta

INSTRUMENTED_COMPONENTS: Final = ("text_encoder", "clip", "vae", "model")


class TensorInspector(Protocol):
    """Tensor checks the probe needs. Implementations must never log or return tensor values."""

    def tensor_meta(self, tensor: Any) -> TensorMeta: ...

    def clip_input_matches(self, clip_input: Any, reference: Any) -> bool:
        """The CLIP input is exactly ``reference`` with a singleton frame axis (L236)."""
        ...

    def vae_input_matches(self, vae_input: Any, reference: Any, frame_count: int) -> bool:
        """Frame 0 is the bicubic resize of ``reference``; the other frames are zero (L240-L248)."""
        ...

    def vae_condition_matches(self, condition: Any, encoded: Any) -> bool:
        """``condition`` is the 4 mask channels followed by exactly ``encoded`` (L249)."""
        ...


class _Delegate:
    """Forwards every attribute to the wrapped upstream component."""

    __slots__ = ("_probe", "_target")

    def __init__(self, target: Any, probe: ConditioningProbe) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_probe", probe)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, value)


class _TextEncoder(_Delegate):
    __slots__ = ()

    def __call__(self, texts: Any, device: Any) -> Any:
        result = self._target(texts, device)
        self._probe._on_text(texts, result)
        return result


class _Clip(_Delegate):
    __slots__ = ()

    def visual(self, videos: Any) -> Any:
        self._probe._on_clip_input(videos)
        result = self._target.visual(videos)
        self._probe._on_clip_output(result)
        return result


class _Vae(_Delegate):
    __slots__ = ()

    def encode(self, videos: Any) -> Any:
        self._probe._on_vae_input(videos)
        result = self._target.encode(videos)
        self._probe._on_vae_output(result)
        return result


class _Denoiser(_Delegate):
    __slots__ = ()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._probe._before_denoiser(kwargs)
        return self._target(*args, **kwargs)


_PROXIES: Final = (
    ("text_encoder", _TextEncoder),
    ("clip", _Clip),
    ("vae", _Vae),
    ("model", _Denoiser),
)


class ConditioningProbe:
    """Observes one ``generate`` call. Single use: install, generate, restore, observation."""

    def __init__(
        self,
        *,
        inspector: TensorInspector,
        reference: Any,
        reference_token: str,
        prompt_text: str,
        negative_prompt: str,
        frame_count: int,
        before_denoiser_call: Callable[[], None],
    ) -> None:
        self._inspector = inspector
        self._reference = reference
        self._token = reference_token
        self._expected_texts = (prompt_text, negative_prompt)
        self._frame_count = frame_count
        self._before_call = before_denoiser_call
        self._pipeline: Any = None
        self._originals: dict[str, Any] = {}
        self._used = False
        self._sources: dict[int, int] = {}
        self._pinned: list[Any] = []  # keeps objects alive so ``id`` values are never reused
        self._text_calls = 0
        self._contexts: list[Any] = []
        self._clip_calls = 0
        self._clip_output: Any = None
        self._vae_calls = 0
        self._encoded: Any = None
        self._vae_condition: Any = None
        self._checked_conditions: set[int] = set()
        self._calls: list[CfgCallObservation] = []
        self._positive_calls = 0

    # -- lifecycle ----------------------------------------------------------------------------

    def install(self, pipeline: Any) -> None:
        if self._used:
            raise RuntimeError("a conditioning probe is single use")
        self._used = True
        self._pipeline = pipeline
        try:
            for name, proxy in _PROXIES:
                original = getattr(pipeline, name)
                setattr(pipeline, name, proxy(original, self))
                self._originals[name] = original
        except BaseException:
            self.restore()
            raise

    def restore(self) -> None:
        """Put the original components back. Safe to call more than once."""
        for name, original in self._originals.items():
            setattr(self._pipeline, name, original)
        self._originals.clear()

    def release(self) -> None:
        """Drop every reference to upstream tensors and the pipeline."""
        self.restore()
        self._pipeline = None
        self._reference = None
        self._pinned.clear()
        self._sources.clear()
        self._contexts.clear()
        self._clip_output = self._encoded = self._vae_condition = None

    def observation(self) -> ConditioningObservation:
        """Metadata for :func:`~frp.baseline.backend.verify_conditioning`, or a violation."""
        problems = []
        if self._text_calls != 2:
            problems.append("the text encoder was not called exactly twice")
        if self._clip_calls != 1 or self._clip_output is None:
            problems.append("the CLIP route was not called exactly once")
        if self._vae_calls != 1 or self._encoded is None:
            problems.append("the VAE first-frame route was not called exactly once")
        if not self._calls:
            problems.append("the denoiser was never called")
        if problems:
            raise ConditioningContractViolation(problems)
        meta = self._inspector.tensor_meta
        clip_route = RouteObservation(
            self._token, meta(self._clip_output), self._source(self._clip_output)
        )
        # Unless the denoiser received a condition built from this encoding, report the bare
        # encoding: its source then matches no denoiser call and verification fails.
        vae_out = self._encoded if self._vae_condition is None else self._vae_condition
        vae_route = RouteObservation(self._token, meta(vae_out), self._source(vae_out))
        return ConditioningObservation(clip_route, vae_route, tuple(self._calls))

    # -- interception -------------------------------------------------------------------------

    def _source(self, obj: Any) -> int:
        key = id(obj)
        if key not in self._sources:
            self._sources[key] = len(self._sources) + 1
            self._pinned.append(obj)
        return self._sources[key]

    def _check(self, check: Callable[..., bool], *args: Any) -> bool:
        try:
            return check(*args) is True
        except Exception:
            return False

    def _on_text(self, texts: Any, result: Any) -> None:
        index = self._text_calls
        self._text_calls += 1
        if index >= len(self._expected_texts):
            raise ConditioningContractViolation(["the text encoder was called more than twice"])
        if not isinstance(texts, Sequence) or list(texts) != [self._expected_texts[index]]:
            branch = "positive prompt" if index == 0 else "config default negative prompt"
            raise ConditioningContractViolation([f"the text encoder did not receive the {branch}"])
        if not isinstance(result, Sequence) or len(result) != 1:
            raise ConditioningContractViolation(["the text encoder returned an unexpected batch"])
        self._contexts.append(result[0])
        self._source(result[0])

    def _on_clip_input(self, videos: Any) -> None:
        self._clip_calls += 1
        if self._clip_calls > 1:
            raise ConditioningContractViolation(["the CLIP route was called more than once"])
        if not (
            isinstance(videos, Sequence)
            and len(videos) == 1
            and self._check(self._inspector.clip_input_matches, videos[0], self._reference)
        ):
            raise ConditioningContractViolation(
                ["the CLIP route did not receive the original reference"]
            )

    def _on_clip_output(self, result: Any) -> None:
        self._clip_output = result
        self._source(result)

    def _on_vae_input(self, videos: Any) -> None:
        self._vae_calls += 1
        if self._vae_calls > 1:
            raise ConditioningContractViolation(["the VAE route was called more than once"])
        if not (
            isinstance(videos, Sequence)
            and len(videos) == 1
            and self._check(
                self._inspector.vae_input_matches, videos[0], self._reference, self._frame_count
            )
        ):
            raise ConditioningContractViolation(
                ["the VAE first-frame route did not receive the original reference"]
            )

    def _on_vae_output(self, result: Any) -> None:
        if not isinstance(result, Sequence) or len(result) != 1:
            raise ConditioningContractViolation(["the VAE route returned an unexpected batch"])
        self._encoded = result[0]
        self._source(result[0])

    def _before_denoiser(self, kwargs: dict[str, Any]) -> None:
        self._before_call()  # stop signal and deadline; may raise
        context, clip_fea, y = kwargs.get("context"), kwargs.get("clip_fea"), kwargs.get("y")
        if (
            not isinstance(context, Sequence)
            or len(context) != 1
            or clip_fea is None
            or not isinstance(y, Sequence)
            or len(y) != 1
        ):
            raise ConditioningContractViolation(
                ["a denoiser call lacked text, CLIP or VAE first-frame conditioning"]
            )
        text = context[0]
        branch: CfgBranch
        if len(self._contexts) == 2 and text is self._contexts[0]:
            branch, step = "positive", self._positive_calls
            self._positive_calls += 1
        elif len(self._contexts) == 2 and text is self._contexts[1]:
            branch, step = "negative", self._positive_calls - 1
        else:
            raise ConditioningContractViolation(
                ["a denoiser call received text conditioning from neither CFG branch"]
            )
        condition = y[0]
        self._link_vae_condition(condition)
        meta = self._inspector.tensor_meta
        self._calls.append(
            CfgCallObservation(
                step_index=step,
                branch=branch,
                clip_fea=meta(clip_fea),
                clip_fea_source=self._source(clip_fea),
                y=meta(condition),
                y_source=self._source(condition),
                context=meta(text),
            )
        )

    def _link_vae_condition(self, condition: Any) -> None:
        """Adopt the first denoiser ``y`` built from this VAE encoding as the route output."""
        if self._vae_condition is not None or self._encoded is None:
            return
        self._source(condition)
        if id(condition) in self._checked_conditions:
            return
        self._checked_conditions.add(id(condition))
        if self._check(self._inspector.vae_condition_matches, condition, self._encoded):
            self._vae_condition = condition


__all__ = ["INSTRUMENTED_COMPONENTS", "ConditioningProbe", "TensorInspector"]
