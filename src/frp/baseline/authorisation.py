"""Private authorisation contract for baseline execution (an interface, not an approval).

Execution needs a **distinct, human-controlled, private** grant that names the specific run and
carries a reference to each of the seven separate human approvals in
:data:`frp.readiness.GATE_IDS` (licence and intended use; consent and data processing; restricted
storage, retention and deletion; cloud-provider terms; quote and budget cap; checkpoint download
and hashing; the GPU smoke test). The grant is bound to the manifest and generation-controls
hashes, the pinned source commit and checkpoint revision, the approved software-environment
digest and the **private expected per-file weight hashes**, so approving one run, plan or weight set
never covers another.

What this repository deliberately does **not** do:

* It provides no provider that grants anything. :class:`DenyAllAuthorisation` is the default and
  the only provider shipped here. Establishing a real, reviewable private provider (who may issue
  grants, how they are signed and stored) is an open integration point for a later, separately
  reviewed change.
* It never treats a passing ``frp readiness`` result, a populated manifest, an environment flag, a
  merged PR or a passing test as permission. Readiness schema 1.0 stays fully ``pending``.
* It never stores approvals, consent records, quotes or provider details in public files. The
  record references below are opaque identifiers of records held in private storage.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from frp.baseline.manifest import RelativeFilePath
from frp.baseline.results import BaselineRunId
from frp.manifest import GitSha, Sha256Hex
from frp.readiness import GATE_IDS, GateId

ExecutorMode = Literal["mock", "live"]
RecordRef = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")]

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class AuthorisationRequest:
    """What an execution entry point asks a provider to authorise (no media, no prompt text)."""

    run_id: str
    run_role: str
    executor_mode: ExecutorMode
    manifest_sha256: str
    generation_controls_sha256: str
    source_commit: str
    checkpoint_revision: str
    environment_sha256: str
    expected_files: Mapping[str, str] = field(repr=False)


class PrivateAuthorisation(BaseModel):
    """A private grant for named runs. Constructing one in public code grants nothing real."""

    model_config = _STRICT

    authorisation_id: RecordRef
    executor_mode: ExecutorMode
    run_ids: Annotated[tuple[BaselineRunId, ...], Field(min_length=1)]
    manifest_sha256: Sha256Hex
    generation_controls_sha256: Sha256Hex
    source_commit: GitSha
    checkpoint_revision: GitSha
    environment_sha256: Sha256Hex
    # The separately approved expected hash of every checkpoint file (private, not this repo).
    expected_files: Annotated[dict[RelativeFilePath, Sha256Hex], Field(min_length=1)]
    # One opaque private record reference per gate; each gate is a separate approval.
    gates: dict[GateId, RecordRef]
    # Human-approved wall-clock cap for one attempt (the budget/provider gates' time bound).
    max_attempt_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def _every_gate_present(self) -> PrivateAuthorisation:
        missing = [gate for gate in GATE_IDS if gate not in self.gates]
        if missing:
            raise ValueError("missing gate approval reference(s): " + ", ".join(missing))
        return self


class AuthorisationProvider(Protocol):
    """Human-controlled source of private grants. Return ``None`` to deny."""

    def authorise(self, request: AuthorisationRequest) -> PrivateAuthorisation | None: ...


class DenyAllAuthorisation:
    """Default provider: authorises nothing. The only provider shipped in this repository."""

    def authorise(self, request: AuthorisationRequest) -> PrivateAuthorisation | None:
        return None


def authorisation_problems(
    grant: PrivateAuthorisation | None, request: AuthorisationRequest
) -> list[str]:
    """Why ``grant`` does not permit exactly this request (empty means it does).

    Messages are fixed strings: they never echo grant contents, record references or hashes.
    """
    if not isinstance(grant, PrivateAuthorisation):
        return ["no private authorisation was provided for this run"]
    problems = []
    checks = (
        ("executor mode", grant.executor_mode, request.executor_mode),
        ("manifest hash", grant.manifest_sha256, request.manifest_sha256),
        (
            "generation controls hash",
            grant.generation_controls_sha256,
            request.generation_controls_sha256,
        ),
        ("source commit", grant.source_commit, request.source_commit),
        ("checkpoint revision", grant.checkpoint_revision, request.checkpoint_revision),
        ("environment digest", grant.environment_sha256, request.environment_sha256),
        ("expected weight files", grant.expected_files, dict(request.expected_files)),
    )
    problems.extend(
        f"authorisation {name} does not match the plan" for name, got, want in checks if got != want
    )
    if request.run_id not in grant.run_ids:
        problems.append("authorisation does not name this run")
    return problems
