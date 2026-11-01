"""Fail-closed access control for opening a review store (V1, V2, V6, V7, V8, V11).

Two paths, never mixed:

* **Synthetic demo stores** (``content_class: synthetic``) may be opened anywhere, including a
  Codespace, but only if *every* registered frame digest equals a frame that the procedural demo
  generator in :mod:`frp.review.demo` produces. Because the viewer also checks each file against its
  registered digest before serving it, a store labelled synthetic cannot be used to show real
  media.
* **Identifiable stores** need, all at once: a storage approval reference in the catalogue; no
  remote, hosted or CI environment indicator; a store directory outside any git working tree and
  not accessible to group or others; and a private, unexpired :class:`ReviewAccessGrant` from a
  :class:`ReviewAccessProvider` that names this store, mode and reviewer role code and cites the
  consent and storage approvals. Only :class:`DenyAllReviewAccess` ships, so identifiable media
  cannot be opened by this release. Designing a real provider is a separately reviewed step.

A grant is an interface, not an approval: nothing here records or infers consent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Final, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from frp.baseline.authorisation import RecordRef
from frp.review.records import ReviewerRoleCode, ReviewMode
from frp.review.security import (
    group_or_world_accessible,
    inside_git_worktree,
    remote_environment_indicators,
)
from frp.review.store import ContentClass, ReviewCatalogue, ReviewStore

ReviewGate = Literal["consent_and_data_processing", "restricted_storage_retention_deletion"]
REVIEW_GATES: Final[tuple[ReviewGate, ...]] = (
    "consent_and_data_processing",
    "restricted_storage_retention_deletion",
)

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


class ReviewAccessDenied(Exception):
    """Opening the store was refused. ``problems`` are fixed descriptions without paths."""

    def __init__(self, problems: list[str] | tuple[str, ...]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True, slots=True)
class ReviewAccessRequest:
    store_id: str
    content_class: ContentClass
    storage_approval_reference: str | None
    mode: ReviewMode
    reviewer_role_code: str
    session_id: str


class ReviewAccessGrant(BaseModel):
    """A private, human-issued grant to open one store. Constructing one grants nothing real."""

    model_config = _STRICT

    grant_id: RecordRef
    store_id: str
    storage_approval_reference: RecordRef
    modes: Annotated[tuple[ReviewMode, ...], Field(min_length=1)]
    reviewer_role_codes: Annotated[tuple[ReviewerRoleCode, ...], Field(min_length=1)]
    gates: dict[ReviewGate, RecordRef]
    expires_at: AwareDatetime


class ReviewAccessProvider(Protocol):
    """Human-controlled source of private review grants. Return ``None`` to deny."""

    def authorise(self, request: ReviewAccessRequest) -> ReviewAccessGrant | None: ...


class DenyAllReviewAccess:
    """Default provider: grants nothing. The only provider shipped in this repository."""

    def authorise(self, request: ReviewAccessRequest) -> ReviewAccessGrant | None:
        return None


def grant_problems(
    grant: ReviewAccessGrant | None, request: ReviewAccessRequest, now: datetime
) -> list[str]:
    if not isinstance(grant, ReviewAccessGrant):
        return ["no private review-access grant was provided for this store and reviewer"]
    problems = []
    if grant.store_id != request.store_id:
        problems.append("the grant names a different store")
    if grant.storage_approval_reference != request.storage_approval_reference:
        problems.append("the grant cites a different storage approval")
    if request.mode not in grant.modes:
        problems.append("the grant does not cover this review mode")
    if request.reviewer_role_code not in grant.reviewer_role_codes:
        problems.append("the grant does not name this reviewer role code")
    if missing := [gate for gate in REVIEW_GATES if gate not in grant.gates]:
        problems.append("the grant lacks approval reference(s): " + ", ".join(missing))
    if grant.expires_at <= now:
        problems.append("the grant has expired")
    return problems


def synthetic_store_problems(catalogue: ReviewCatalogue) -> list[str]:
    """Why a store labelled synthetic is not verifiably the procedural demo content."""
    from frp.review.demo import demo_frame_digests

    if not catalogue.simulated:
        return ["a synthetic store must hold simulated results"]
    allowed = demo_frame_digests()
    registered = {d for entry in catalogue.media.values() for d in entry.frame_sha256}
    if not registered <= allowed:
        return ["media in a store labelled synthetic are not procedurally generated demo frames"]
    return []


def authorise_review(
    store: ReviewStore,
    catalogue: ReviewCatalogue,
    request: ReviewAccessRequest,
    provider: ReviewAccessProvider,
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    """Raise :class:`ReviewAccessDenied` unless every applicable check passes."""
    if catalogue.content_class == "synthetic":
        problems = synthetic_store_problems(catalogue)
    else:
        problems = []
        if indicators := remote_environment_indicators(environ):
            problems.append(
                "identifiable media may be opened only on an approved local reviewer machine; "
                "remote, hosted or CI environment indicated by: " + ", ".join(indicators)
            )
        if inside_git_worktree(store.root):
            problems.append("the store is inside a git working tree (risk of committing media)")
        if group_or_world_accessible(store.root):
            problems.append("the store directory is accessible to group or others")
        grant = provider.authorise(request)
        problems.extend(grant_problems(grant, request, now or datetime.now(UTC)))
    if problems:
        raise ReviewAccessDenied(problems)


__all__ = [
    "REVIEW_GATES",
    "DenyAllReviewAccess",
    "ReviewAccessDenied",
    "ReviewAccessGrant",
    "ReviewAccessProvider",
    "ReviewAccessRequest",
    "authorise_review",
    "grant_problems",
    "synthetic_store_problems",
]
