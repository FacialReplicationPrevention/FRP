"""Fail-closed Wan 2.1 baseline executor over an injected backend.

Every ``execute`` call runs the same ordered gates; any failure before generation raises
:class:`~frp.baseline.interfaces.ExecutionRefused` and **nothing is loaded or generated**:

1. the manifest is complete (``NOT EXECUTION READY`` otherwise) and the run belongs to it;
2. a private authorisation, supplied by an ``AuthorisationProvider``, permits this specific
   run, manifest, controls, pins, environment digest and expected weight hashes and references
   all seven human gates (the default provider denies everything);
3. no prompt-extension or remote-service module is already imported;
4. the backend reports its dependencies available (the shipped upstream backend is disabled);
5. the source checkout is clean and at the pinned commit;
6. the backend's reported software-environment digest equals the approved one;
7. **every** local checkpoint file matches its approved SHA-256 (nothing extra, nothing missing).

Only then is the backend asked to load (from a :class:`~frp.baseline.preflight.VerifiedCheckpoint`)
and generate, with network access blocked. The returned conditioning metadata and output shape are
verified; a violation turns the attempt into a failure with no artefact. Cleanup always runs.

Using a mock backend exercises this control flow on CPU. A mock's successful outcome is **not** a
Wan 2.1 inference: results from a non-live backend are marked ``simulated``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from frp.baseline.authorisation import (
    AuthorisationProvider,
    AuthorisationRequest,
    DenyAllAuthorisation,
    PrivateAuthorisation,
    authorisation_problems,
)
from frp.baseline.backend import (
    ConditioningContractViolation,
    GenerationInterrupted,
    GenerationOutput,
    GenerationRequest,
    GenerationResourceExhausted,
    GenerationTimeout,
    LiveExecutionDisabled,
    ModelLoadError,
    ReferenceHandle,
    ReferenceProvider,
    StopReasonCode,
    StopSignal,
    Wan21Backend,
    output_problems,
    verify_conditioning,
)
from frp.baseline.interfaces import BaselineExecutionOutcome, ExecutionRefused
from frp.baseline.manifest import (
    BaselineManifest,
    baseline_controls_sha256,
    baseline_manifest_sha256,
    unset_execution_fields,
)
from frp.baseline.planner import BaselinePlannedRun
from frp.baseline.preflight import (
    GitSourceInspector,
    PreflightError,
    RemoteAccessBlocked,
    SourceInspector,
    VerifiedCheckpoint,
    network_blocked,
    prohibited_modules_loaded,
    verify_checkpoint_files,
    weight_files_sha256,
)
from frp.baseline.protocol import BASELINE_MODEL_FAMILY, BASELINE_SCHEMA_VERSION, WAN21_MAX_AREA
from frp.baseline.results import (
    FAILURE_CATEGORY_FOR_DETAIL,
    ConditioningSummary,
    ExecutionProvenance,
    FailureDetail,
)
from frp.results import ArtefactRef, ExecutionRecord, ExecutorInfo

EXECUTOR_NAME = "frp-wan21-baseline-executor"


class _NoStop:
    def reason(self) -> StopReasonCode | None:
        return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Wan21BaselineExecutor:
    """Executes planned baseline runs through an injected backend. See the module docstring."""

    def __init__(
        self,
        *,
        manifest: BaselineManifest,
        backend: Wan21Backend,
        references: ReferenceProvider,
        checkpoint_dir: Path,
        source_dir: Path,
        artefact_base_uri: str,
        authorisation: AuthorisationProvider | None = None,
        source_inspector: SourceInspector | None = None,
        stop: StopSignal | None = None,
        clock: Callable[[], datetime] = _utc_now,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        # Validates the private base URI shape once, up front (no path ever reaches a record).
        ArtefactRef(uri=f"{artefact_base_uri.rstrip('/')}/probe")
        self._manifest = manifest
        self._manifest_sha256 = baseline_manifest_sha256(manifest)
        self._controls_sha256 = baseline_controls_sha256(manifest)
        self._backend = backend
        self._references = references
        self._checkpoint_dir = checkpoint_dir
        self._source_dir = source_dir
        self._base_uri = artefact_base_uri.rstrip("/")
        self._authorisation = authorisation or DenyAllAuthorisation()
        self._inspector = source_inspector or GitSourceInspector()
        self._stop: StopSignal = stop or _NoStop()
        self._clock = clock
        self._timer = timer
        self._mode = "live" if backend.info.live else "mock"
        self._used_attempts: set[tuple[str, int]] = set()
        self._verified: VerifiedCheckpoint | None = None
        self._provenance: ExecutionProvenance | None = None
        self._refusal: ExecutionRefused | None = None
        self._loaded = False
        self._closed = False

    @property
    def info(self) -> ExecutorInfo:
        return ExecutorInfo(
            name=EXECUTOR_NAME,
            revision=BASELINE_SCHEMA_VERSION,
            model_family=BASELINE_MODEL_FAMILY,
            simulated=not self._backend.info.live,
        )

    @property
    def verified_provenance(self) -> ExecutionProvenance | None:
        return self._provenance

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._backend.close()

    def __enter__(self) -> Wan21BaselineExecutor:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- gates ------------------------------------------------------------------------------

    def _check_run(self, run: BaselinePlannedRun, attempt_index: int) -> None:
        if attempt_index < 1:
            raise ValueError("attempt_index must be >= 1")
        if (run.run_id, attempt_index) in self._used_attempts:
            raise ValueError("this attempt was already executed; attempts are never overwritten")
        if (
            run.generation_controls_sha256 != self._controls_sha256
            or run.run_role != self._manifest.run_role
            or not 1 <= run.prompt_index <= len(self._manifest.prompts)
            or self._manifest.prompts[run.prompt_index - 1].id != run.prompt_id
        ):
            raise ExecutionRefused("invalid_input")

    def _authorise(self, run: BaselinePlannedRun) -> PrivateAuthorisation:
        m = self._manifest
        request = AuthorisationRequest(
            run_id=run.run_id,
            run_role=run.run_role,
            executor_mode=self._mode,  # type: ignore[arg-type]
            manifest_sha256=self._manifest_sha256,
            generation_controls_sha256=self._controls_sha256,
            source_commit=m.upstream_commit_sha or "",
            checkpoint_revision=m.checkpoint_revision or "",
            environment_sha256=m.software_environment_hash or "",
            expected_files=dict(m.checkpoint_hashes or {}),
        )
        try:
            grant = self._authorisation.authorise(request)
        except Exception:
            raise ExecutionRefused("not_authorised") from None
        if authorisation_problems(grant, request):
            raise ExecutionRefused("not_authorised")
        return grant  # type: ignore[return-value]

    def _prepare(self, grant: PrivateAuthorisation) -> None:
        """Verify everything that must hold before loading; runs once, failure is remembered."""
        if self._refusal is not None:
            raise self._refusal
        if self._verified is not None:
            return
        try:
            self._prepare_checks(grant)
        except ExecutionRefused as refusal:
            self._refusal = refusal
            raise

    def _prepare_checks(self, grant: PrivateAuthorisation) -> None:
        m = self._manifest
        if prohibited_modules_loaded():
            raise ExecutionRefused("prohibited_module_loaded")
        try:
            self._backend.check_available()
        except LiveExecutionDisabled:
            raise ExecutionRefused("live_execution_disabled") from None
        except Exception:
            raise ExecutionRefused("backend_unavailable") from None
        commit = self._inspector.head_commit(self._source_dir)
        if commit != m.upstream_commit_sha or not self._inspector.is_clean(self._source_dir):
            raise ExecutionRefused("provenance_mismatch")
        try:
            environment = self._backend.environment_sha256()
        except Exception:
            raise ExecutionRefused("backend_unavailable") from None
        if environment != m.software_environment_hash:
            raise ExecutionRefused("provenance_mismatch")
        try:
            verified = verify_checkpoint_files(self._checkpoint_dir, grant.expected_files)
        except PreflightError:
            raise ExecutionRefused("weights_verification_failed") from None
        self._verified = verified
        self._provenance = ExecutionProvenance(
            source_commit=grant.source_commit,
            checkpoint_revision=grant.checkpoint_revision,
            weight_files_sha256=weight_files_sha256(grant.expected_files),
            environment_sha256=environment,
            verified_before_load=True,
        )

    # -- attempt ----------------------------------------------------------------------------

    def execute(self, run: BaselinePlannedRun, attempt_index: int) -> BaselineExecutionOutcome:
        self._check_run(run, attempt_index)
        if unset_execution_fields(self._manifest):
            raise ExecutionRefused("not_execution_ready")
        grant = self._authorise(run)
        self._prepare(grant)
        try:
            reference = self._references.reference_for(run.identity_pseudonym)
            if not isinstance(reference, ReferenceHandle):
                raise LookupError
        except Exception:
            raise ExecutionRefused("invalid_input") from None
        self._used_attempts.add((run.run_id, attempt_index))
        request = self._build_request(run, attempt_index, reference, grant)
        return self._run_attempt(request)

    def _build_request(
        self,
        run: BaselinePlannedRun,
        attempt_index: int,
        reference: ReferenceHandle,
        grant: PrivateAuthorisation,
    ) -> GenerationRequest:
        m = self._manifest
        return GenerationRequest(
            run_id=run.run_id,
            attempt_index=attempt_index,
            reference=reference,
            prompt_text=m.prompts[run.prompt_index - 1].text,
            seed=run.seed,
            max_area=WAN21_MAX_AREA[m.resolution or ""],
            frame_count=m.frame_count or 0,
            sample_shift=m.sample_shift or 0.0,
            sample_solver=m.sampler or "",
            sampling_steps=m.sampling_steps or 0,
            guide_scale=m.guidance_scale or 0.0,
            offload_model=bool(m.offload_model),
            output_uri=f"{self._base_uri}/{run.run_id}/attempt-{attempt_index:02d}.mp4",
            deadline_seconds=grant.max_attempt_seconds,
        )

    def _run_attempt(self, request: GenerationRequest) -> BaselineExecutionOutcome:
        started_at = self._clock()
        t0 = self._timer()
        output: GenerationOutput | None = None
        summary: ConditioningSummary | None = None
        detail: FailureDetail | None = None
        blocked_calls = 0
        stage = "load"
        try:
            try:
                with network_blocked() as guard:
                    try:
                        if not self._loaded:
                            if self._verified is None:
                                raise ModelLoadError
                            self._backend.load(self._verified)
                            self._loaded = True
                        stage = "generate"
                        output = self._backend.generate(request, self._stop)
                    finally:
                        blocked_calls = guard.blocked_calls
            except GenerationInterrupted as exc:
                detail = exc.reason
            except GenerationTimeout:
                detail = "timeout"
            except (GenerationResourceExhausted, MemoryError):
                detail = "resource_exhausted"
            except RemoteAccessBlocked:
                detail = "remote_call_blocked"
            except KeyboardInterrupt:
                detail = "operator_abort"
            except Exception:
                detail = "model_load_error" if stage == "load" else "generation_error"
            if blocked_calls:
                detail = "remote_call_blocked"
            elif detail is None and prohibited_modules_loaded():
                detail = "prohibited_module_loaded"
            if detail is None and output is not None:
                detail, summary = self._check_output(output, request)
            elif detail is None:
                detail = "generation_error"
        finally:
            cleanup_ok = self._cleanup()
        finished_at = self._clock()
        wall_seconds = max(0.0, self._timer() - t0)
        if detail is None and output is not None and summary is not None:
            execution = ExecutionRecord(
                status="succeeded",
                artefact=ArtefactRef(uri=output.artefact_uri),
                failure_category=None,
                gpu_seconds=output.gpu_seconds,
            )
        else:
            summary = None
            detail = detail or "generation_error"
            execution = ExecutionRecord(
                status="failed",
                artefact=None,
                failure_category=FAILURE_CATEGORY_FOR_DETAIL[detail],
                gpu_seconds=None,
            )
        return BaselineExecutionOutcome(
            execution=execution,
            failure_detail=None if execution.status == "succeeded" else detail,
            started_at=started_at,
            finished_at=finished_at,
            wall_seconds=wall_seconds,
            conditioning=summary,
            cleanup_ok=cleanup_ok,
        )

    def _check_output(
        self, output: GenerationOutput, request: GenerationRequest
    ) -> tuple[FailureDetail | None, ConditioningSummary | None]:
        try:
            if output_problems(output, request):
                return "output_contract_violation", None
            return None, verify_conditioning(output.observation, request)
        except ConditioningContractViolation:
            return "conditioning_contract_violation", None
        except (TypeError, ValueError, AttributeError):
            return "output_contract_violation", None

    def _cleanup(self) -> bool:
        try:
            self._backend.cleanup()
        except Exception:
            return False
        return True


__all__ = ["EXECUTOR_NAME", "Wan21BaselineExecutor"]
