"""Hardened local private storage for a future private baseline run (CPU-testable, Linux only).

This module is infrastructure, **not** an approval: it contains no grant, no provider and no
activation path, and nothing here makes a private run authorised or scientifically valid. It
implements the storage contract in ``docs/private-execution-security-design.md``:

* a private root that must be Linux, canonical, owner-only and below trusted ancestors;
* an exact ``private://<namespace>/outputs|references/...`` URI grammar, and every filesystem
  operation walked from a root directory descriptor with ``O_NOFOLLOW`` (a symlink swapped into any
  component is refused, never followed);
* **staged** outputs: ``reserve`` creates an exclusive owner-only partial file, and a later
  ``commit`` publishes it by identity-checked, no-replace ``link(2)`` (so an executor can reject a
  result *before* anything is published), with an inode-checked ``rollback``;
* a keyed attempt ledger (attempt markers and withdrawal tombstones named by an HMAC token, never by
  run id) that deletion and withdrawal never reopen, and an irreversible ``erase_store``;
* durability: file data and parent directory entries are fsynced before a promise is made.

Platform assumptions (not claimed beyond them): Linux local block storage with working ``link``,
``O_EXCL`` and ``fsync``. POSIX mode bits are **not** treated as NTFS or macOS ACLs; other platforms
are refused. Network, FUSE and shared filesystems are unsupported and **cannot be detected here**;
a private gate must attest that the volume is local. A same-uid process or root is outside the
threat model (the encoder is also handed a path), see the design note.

Messages are fixed strings: they never contain a path, URI, run id, name or ledger token.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import secrets
import stat
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, Protocol

from frp.review.security import inside_git_worktree

MAX_REFERENCE_BYTES: Final = 32 * 1024 * 1024
KEY_BYTES: Final = 32
KEY_FILE: Final = "ledger.key"
ERASED_FILE: Final = "ERASED"
WITHDRAWN_FILE: Final = "withdrawn"

_COMPONENT: Final = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_RUN_ID: Final = r"[A-Z0-9][A-Z0-9-]{2,63}-R[0-9]{4,}"
_NAMESPACE_RE: Final = re.compile(_COMPONENT)
_RUN_ID_RE: Final = re.compile(_RUN_ID)
_OUTPUT_URI_RE: Final = re.compile(
    rf"private://(?P<ns>{_COMPONENT})/outputs/(?P<run>{_RUN_ID})/attempt-(?P<n>[0-9]{{2}})\.mp4",
    re.ASCII,
)
_REFERENCE_URI_RE: Final = re.compile(
    rf"private://(?P<ns>{_COMPONENT})/references/(?P<name>{_COMPONENT}\.(?:png|jpg|jpeg))",
    re.ASCII,
)
_DIR_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_MAX_ATTEMPT_INDEX: Final = 99

ReceiptKind = Literal["output", "reference", "run", "store"]
ReceiptOutcome = Literal["deleted", "absent", "erased"]


class StorageError(Exception):
    """A storage refusal or failure. The message is a fixed string and never contains a path."""


# -- posture checks ---------------------------------------------------------------------------


def _platform_problem() -> str | None:
    if sys.platform != "linux":
        return (
            "private storage is supported on Linux only; POSIX mode bits are not NTFS or macOS "
            "ACLs and cannot be verified here"
        )
    needed = (os.open, os.mkdir, os.unlink, os.rmdir, os.stat)
    if not all(call in os.supports_dir_fd for call in needed) or (
        os.link not in os.supports_follow_symlinks
    ):
        return "this platform lacks the directory-descriptor primitives private storage needs"
    return None


def _ancestor_problems(path: Path) -> list[str]:
    """Ancestors must be root/uid-owned and not group/other-writable (sticky exception below)."""
    euid = os.geteuid()
    problems: list[str] = []
    child = path
    for parent in path.parents:
        try:
            parent_stat = os.lstat(parent)
            child_stat = os.lstat(child)
        except OSError:
            return ["a parent directory could not be inspected"]
        if not stat.S_ISDIR(parent_stat.st_mode):
            problems.append("a parent of the path is not a directory")
        if parent_stat.st_uid not in (0, euid):
            problems.append("a parent directory is owned by another user")
        if parent_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            # In a sticky directory only the entry's owner (or the directory's) may rename or
            # remove it, so a writable sticky ancestor such as /tmp is safe only above an entry
            # that we (or root) own.
            sticky_ok = bool(parent_stat.st_mode & stat.S_ISVTX) and child_stat.st_uid in (
                0,
                euid,
            )
            if not sticky_ok:
                problems.append("a parent directory is writable by group or others")
        child = parent
    return sorted(set(problems))


def private_root_problems(path: Path) -> list[str]:
    """Why ``path`` is not an acceptable private store root (empty means acceptable)."""
    if platform_problem := _platform_problem():
        return [platform_problem]
    if not path.is_absolute() or os.path.realpath(path) != str(path):
        return ["the private root must be an absolute, canonical path without symlinked parts"]
    try:
        root_stat = os.lstat(path)
    except OSError:
        return ["the private root does not exist"]
    problems = []
    if not stat.S_ISDIR(root_stat.st_mode):
        problems.append("the private root is not a directory")
    if root_stat.st_uid != os.geteuid():
        problems.append("the private root is not owned by the running user")
    if root_stat.st_mode & 0o077:
        problems.append("the private root is accessible to group or others")
    problems.extend(_ancestor_problems(path))
    if inside_git_worktree(path):
        problems.append("the private root is inside a git working tree")
    return problems


def trusted_tree_problems(root: Path) -> list[str]:
    """Why a source or checkpoint tree cannot be trusted not to change under us.

    Applies to the root, its ancestors and **every** entry (including ``.git`` and ``.cache``,
    without following links): no symbolic link anywhere, no special file, every owner the running
    user or root, nothing writable by group or others. Messages are counts/fixed text.
    """
    if os.name != "posix":
        return ["tree ownership checks require a POSIX host"]
    if not root.is_absolute() or os.path.realpath(root) != str(root):
        return ["the tree path must be absolute and canonical (no symlinked parts)"]
    euid = os.geteuid()
    links = special = foreign = writable = 0
    try:
        entries = [(root, os.lstat(root))]
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            entries.extend(
                (Path(directory, name), os.lstat(Path(directory, name)))
                for name in (*dirnames, *filenames)
            )
    except OSError:
        return ["the tree could not be fully inspected"]
    for _path, info in entries:
        mode = info.st_mode
        if stat.S_ISLNK(mode):
            links += 1
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            special += 1
        if info.st_uid not in (0, euid):
            foreign += 1
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            writable += 1
    problems = _ancestor_problems(root)
    if links:
        problems.append(f"{links} symbolic link(s) found in the tree")
    if special:
        problems.append(f"{special} special file(s) found in the tree")
    if foreign:
        problems.append(f"{foreign} entr(ies) owned by another user")
    if writable:
        problems.append(f"{writable} entr(ies) writable by group or others")
    return problems


# -- protocols the adapter sees -----------------------------------------------------------------


@dataclass(eq=False)
class Reservation:
    """A staged output: an exclusive partial file plus its ledger marker. Never repr'd."""

    run_id: str = field(repr=False)
    attempt_index: int
    uri: str = field(repr=False)
    partial_path: Path = field(repr=False)
    _partial_id: tuple[int, int] = field(repr=False)
    committed_id: tuple[int, int] | None = field(default=None, repr=False)


class OutputStore(Protocol):
    """What the adapter may do with outputs. No deletion, withdrawal or enumeration lives here."""

    def problems(self) -> list[str]: ...

    def check_reservable(self, uri: str) -> None:
        """Raise :class:`StorageError` unless a reservation could now succeed (changes nothing)."""
        ...

    def reserve(self, uri: str) -> Reservation: ...

    def commit(self, reservation: Reservation) -> None: ...

    def discard(self, reservation: Reservation) -> None:
        """Remove the staged partial. Idempotent; never touches a committed final."""
        ...

    def rollback(self, reservation: Reservation) -> None:
        """Remove a committed final only if it is still the file this reservation committed."""
        ...


class ReferenceReader(Protocol):
    def problems(self) -> list[str]: ...

    def read(self, uri: str, *, max_bytes: int = MAX_REFERENCE_BYTES) -> bytes:
        """Read a private reference (bounded, no-follow, regular owner-only file)."""
        ...


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    """Content-free proof of a deletion: no URI, path, run id, pseudonym, token or hash."""

    kind: ReceiptKind
    outcome: ReceiptOutcome
    at: datetime


class _PlannedRun(Protocol):
    @property
    def run_id(self) -> str: ...

    @property
    def identity_pseudonym(self) -> str: ...


def withdrawal_run_ids(runs: Iterable[_PlannedRun], pseudonym: str) -> tuple[str, ...]:
    """Every planned run of one identity, executed or not (pure; for ``withdraw``)."""
    return tuple(run.run_id for run in runs if run.identity_pseudonym == pseudonym)


# -- the store -----------------------------------------------------------------------------------


def _parse_output(uri: str, namespace: str) -> tuple[str, int]:
    match = _OUTPUT_URI_RE.fullmatch(uri) if isinstance(uri, str) else None
    index = int(match["n"]) if match else 0
    if match is None or match["ns"] != namespace or not 1 <= index <= _MAX_ATTEMPT_INDEX:
        raise StorageError("the output location is not a valid private location")
    return match["run"], index


def _parse_reference(uri: str, namespace: str) -> str:
    match = _REFERENCE_URI_RE.fullmatch(uri) if isinstance(uri, str) else None
    if match is None or match["ns"] != namespace:
        raise StorageError("the reference location is not a valid private location")
    return match["name"]


def _partial_name(index: int) -> str:
    return f".attempt-{index:02d}.partial.mp4"


def _final_name(index: int) -> str:
    return f"attempt-{index:02d}.mp4"


def _fsync_dir(fd: int) -> None:
    os.fsync(fd)


def _exists(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


class LocalPrivateStore:
    """Private output/reference store under one owner-only root. Construction does no I/O."""

    def __init__(
        self,
        root: Path,
        namespace: str,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not _NAMESPACE_RE.fullmatch(namespace):
            raise StorageError("the namespace is not valid")
        self._root = Path(root)
        self._namespace = namespace
        self._clock = clock

    def __repr__(self) -> str:
        return "LocalPrivateStore(...)"

    # -- descriptors and ledger helpers ----------------------------------------------------

    def problems(self) -> list[str]:
        problems = private_root_problems(self._root)
        if problems:
            return problems
        try:
            with self._root_fd(check_posture=False) as root_fd:
                if _exists(root_fd, ERASED_FILE):
                    return ["the store was erased and can never be used again"]
                if _exists(root_fd, "ledger") and self._load_key(root_fd, create=False) is None:
                    return ["the attempt ledger exists but its key is missing"]
        except (StorageError, OSError):
            return ["the private store could not be inspected safely"]
        return []

    @contextlib.contextmanager
    def _root_fd(self, *, check_posture: bool = True, allow_erased: bool = False) -> Iterator[int]:
        if check_posture and private_root_problems(self._root):
            raise StorageError("the private store root is not acceptable")
        try:
            fd = os.open(self._root, _DIR_FLAGS)
        except OSError:
            raise StorageError("the private store root could not be opened") from None
        try:
            self._verify_dir(fd)
            if not allow_erased and _exists(fd, ERASED_FILE):
                raise StorageError("the store was erased and can never be used again")
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def _verify_dir(fd: int) -> None:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise StorageError("a private directory is not owner-only")

    def _subdir(self, parent_fd: int, name: str, *, create: bool) -> int | None:
        """Open (and verify) a child directory; ``None`` if absent and ``create`` is false."""
        created = False
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
                created = True
            except FileExistsError:
                pass
        try:
            fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError:
            raise StorageError("a private directory could not be opened safely") from None
        try:
            self._verify_dir(fd)
            if created:
                _fsync_dir(parent_fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _load_key(self, root_fd: int, *, create: bool) -> bytes | None:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        for _ in range(2):
            try:
                fd = os.open(KEY_FILE, flags, dir_fd=root_fd)
            except FileNotFoundError:
                if not create:
                    return None
                if _exists(root_fd, "ledger"):
                    # A new key would silently orphan every spent attempt and withdrawal.
                    raise StorageError("the attempt ledger exists but its key is missing") from None
                self._create_key(root_fd)
                continue
            except OSError:
                raise StorageError("the ledger key could not be opened safely") from None
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077
                    or info.st_nlink != 1
                    or info.st_size != KEY_BYTES
                ):
                    raise StorageError("the ledger key is not an owner-only file of the right size")
                key = os.read(fd, KEY_BYTES + 1)
            finally:
                os.close(fd)
            if len(key) != KEY_BYTES:
                raise StorageError("the ledger key is not an owner-only file of the right size")
            return key
        raise StorageError("the ledger key could not be created")

    @staticmethod
    def _create_key(root_fd: int) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(KEY_FILE, flags, 0o600, dir_fd=root_fd)
        except FileExistsError:
            return
        try:
            os.write(fd, secrets.token_bytes(KEY_BYTES))
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(root_fd)

    @staticmethod
    def _token(key: bytes, run_id: str) -> str:
        return hmac.new(key, b"run:" + run_id.encode("ascii"), hashlib.sha256).hexdigest()

    def _run_ledger(self, root_fd: int, run_id: str, *, create: bool) -> int | None:
        """Open ``ledger/<token>``; ``None`` if absent (never raises for absence)."""
        key = self._load_key(root_fd, create=create)
        if key is None:
            if _exists(root_fd, "ledger"):
                raise StorageError("the attempt ledger exists but its key is missing")
            return None
        ledger_fd = self._subdir(root_fd, "ledger", create=create)
        if ledger_fd is None:
            return None
        try:
            return self._subdir(ledger_fd, self._token(key, run_id), create=create)
        finally:
            os.close(ledger_fd)

    @staticmethod
    def _touch_exclusive(dir_fd: int, name: str, mode: int) -> tuple[int, int] | None:
        """Create ``name`` exclusively (no-follow); ``None`` if it exists. Returns (dev, ino)."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(name, flags, mode, dir_fd=dir_fd)
        except FileExistsError:
            return None
        try:
            os.fchmod(fd, mode)
            os.fsync(fd)
            info = os.fstat(fd)
        finally:
            os.close(fd)
        _fsync_dir(dir_fd)
        return info.st_dev, info.st_ino

    def _is_withdrawn(self, root_fd: int, run_id: str) -> bool:
        ledger_fd = self._run_ledger(root_fd, run_id, create=False)
        if ledger_fd is None:
            return False
        try:
            return _exists(ledger_fd, WITHDRAWN_FILE)
        finally:
            os.close(ledger_fd)

    # -- OutputStore -----------------------------------------------------------------------

    def check_reservable(self, uri: str) -> None:
        run_id, index = _parse_output(uri, self._namespace)
        try:
            with self._root_fd() as root_fd:
                ledger_fd = self._run_ledger(root_fd, run_id, create=False)
                if ledger_fd is not None:
                    try:
                        if _exists(ledger_fd, WITHDRAWN_FILE):
                            raise StorageError("this run was withdrawn and can never run again")
                        if _exists(ledger_fd, f"attempt-{index:02d}"):
                            raise StorageError("this attempt index is already spent")
                    finally:
                        os.close(ledger_fd)
                outputs_fd = self._subdir(root_fd, "outputs", create=False)
                if outputs_fd is None:
                    return
                try:
                    run_fd = self._subdir(outputs_fd, run_id, create=False)
                finally:
                    os.close(outputs_fd)
                if run_fd is None:
                    return
                try:
                    if _exists(run_fd, _final_name(index)) or _exists(run_fd, _partial_name(index)):
                        raise StorageError("an output already exists for this attempt")
                finally:
                    os.close(run_fd)
        except OSError:
            raise StorageError("the output location could not be checked") from None

    def reserve(self, uri: str) -> Reservation:
        run_id, index = _parse_output(uri, self._namespace)
        try:
            return self._reserve(run_id, index, uri)
        except OSError:
            raise StorageError("the output could not be reserved") from None

    def _reserve(self, run_id: str, index: int, uri: str) -> Reservation:
        with self._root_fd() as root_fd:
            ledger_fd = self._run_ledger(root_fd, run_id, create=True)
            if ledger_fd is None:  # pragma: no cover - create=True always opens it
                raise StorageError("the attempt ledger is unavailable")
            try:
                if _exists(ledger_fd, WITHDRAWN_FILE):
                    raise StorageError("this run was withdrawn and can never run again")
                if self._touch_exclusive(ledger_fd, f"attempt-{index:02d}", 0o600) is None:
                    raise StorageError("this attempt index is already spent")
            finally:
                os.close(ledger_fd)
            outputs_fd = self._subdir(root_fd, "outputs", create=True)
            if outputs_fd is None:  # pragma: no cover
                raise StorageError("the outputs directory is unavailable")
            try:
                run_fd = self._subdir(outputs_fd, run_id, create=True)
            finally:
                os.close(outputs_fd)
            if run_fd is None:  # pragma: no cover
                raise StorageError("the run directory is unavailable")
            try:
                if _exists(run_fd, _final_name(index)):
                    raise StorageError("an output already exists for this attempt")
                identity = self._touch_exclusive(run_fd, _partial_name(index), 0o600)
                if identity is None:
                    raise StorageError("a partial output already exists for this attempt")
            finally:
                os.close(run_fd)
        partial_path = self._root / "outputs" / run_id / _partial_name(index)
        return Reservation(run_id, index, uri, partial_path, identity)

    def _run_dir(self, root_fd: int, run_id: str, *, create: bool = False) -> int | None:
        outputs_fd = self._subdir(root_fd, "outputs", create=create)
        if outputs_fd is None:
            return None
        try:
            return self._subdir(outputs_fd, run_id, create=create)
        finally:
            os.close(outputs_fd)

    def commit(self, reservation: Reservation) -> None:
        try:
            self._commit(reservation)
        except OSError:
            raise StorageError("the output could not be committed") from None

    def _commit(self, reservation: Reservation) -> None:
        run_id, index = reservation.run_id, reservation.attempt_index
        partial, final = _partial_name(index), _final_name(index)
        with self._root_fd() as root_fd:
            if self._is_withdrawn(root_fd, run_id):
                raise StorageError("this run was withdrawn; nothing is committed")
            run_fd = self._run_dir(root_fd, run_id)
            if run_fd is None:
                raise StorageError("the staged output is missing")
            try:
                self._link_into_place(run_fd, partial, final, reservation)
                # A withdrawal that raced the commit wrote its tombstone before enumerating the
                # directory; re-checking after the link closes the window either way.
                if self._is_withdrawn(root_fd, run_id):
                    self._unlink_if_same(run_fd, final, reservation.committed_id)
                    reservation.committed_id = None
                    raise StorageError("this run was withdrawn; nothing is committed")
            finally:
                os.close(run_fd)

    def _link_into_place(
        self, run_fd: int, partial: str, final: str, reservation: Reservation
    ) -> None:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(partial, flags, dir_fd=run_fd)
        except OSError:
            raise StorageError("the staged output is missing or was replaced") from None
        try:
            info = os.fstat(fd)
            if (
                (info.st_dev, info.st_ino) != reservation._partial_id
                or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise StorageError("the staged output is not the file that was reserved")
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            # link(2) never replaces an existing final, unlike rename(2).
            os.link(partial, final, src_dir_fd=run_fd, dst_dir_fd=run_fd, follow_symlinks=False)
        except FileExistsError:
            raise StorageError("a final output already exists; it is never replaced") from None
        reservation.committed_id = reservation._partial_id
        try:
            _fsync_dir(run_fd)
            os.unlink(partial, dir_fd=run_fd)
            _fsync_dir(run_fd)
            final_info = os.stat(final, dir_fd=run_fd, follow_symlinks=False)
            if (
                (final_info.st_dev, final_info.st_ino) != reservation._partial_id
                or final_info.st_nlink != 1
                or not stat.S_ISREG(final_info.st_mode)
            ):
                raise StorageError("the committed output is not the staged file")
        except BaseException:
            self._unlink_if_same(run_fd, final, reservation.committed_id)
            reservation.committed_id = None
            with contextlib.suppress(OSError):
                os.unlink(partial, dir_fd=run_fd)
            raise

    @staticmethod
    def _unlink_if_same(run_fd: int, name: str, identity: tuple[int, int] | None) -> None:
        if identity is None:
            return
        try:
            info = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (info.st_dev, info.st_ino) == identity and stat.S_ISREG(info.st_mode):
            os.unlink(name, dir_fd=run_fd)
            _fsync_dir(run_fd)

    def discard(self, reservation: Reservation) -> None:
        try:
            with self._root_fd() as root_fd:
                run_fd = self._run_dir(root_fd, reservation.run_id)
                if run_fd is None:
                    return
                try:
                    try:
                        os.unlink(_partial_name(reservation.attempt_index), dir_fd=run_fd)
                    except FileNotFoundError:
                        return
                    _fsync_dir(run_fd)
                finally:
                    os.close(run_fd)
        except OSError:
            raise StorageError("the staged output could not be discarded") from None

    def rollback(self, reservation: Reservation) -> None:
        if reservation.committed_id is None:
            return
        try:
            with self._root_fd() as root_fd:
                run_fd = self._run_dir(root_fd, reservation.run_id)
                if run_fd is None:
                    return
                try:
                    self._unlink_if_same(
                        run_fd, _final_name(reservation.attempt_index), reservation.committed_id
                    )
                finally:
                    os.close(run_fd)
        except OSError:
            raise StorageError("the committed output could not be rolled back") from None
        reservation.committed_id = None

    # -- ReferenceReader -------------------------------------------------------------------

    def read(self, uri: str, *, max_bytes: int = MAX_REFERENCE_BYTES) -> bytes:
        name = _parse_reference(uri, self._namespace)
        try:
            with self._root_fd() as root_fd:
                refs_fd = self._subdir(root_fd, "references", create=False)
                if refs_fd is None:
                    raise StorageError("the reference is missing")
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=refs_fd)
                finally:
                    os.close(refs_fd)
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077
                        or info.st_size > max_bytes
                    ):
                        raise StorageError("the reference is not an acceptable private file")
                    data = os.read(fd, max_bytes + 1)
                finally:
                    os.close(fd)
        except OSError:
            raise StorageError("the reference could not be read") from None
        if len(data) > max_bytes:
            raise StorageError("the reference is not an acceptable private file")
        return data

    # -- operator operations (not on the adapter protocols) -----------------------------------

    def _receipt(self, kind: ReceiptKind, deleted: bool) -> DeletionReceipt:
        return DeletionReceipt(
            kind=kind, outcome="deleted" if deleted else "absent", at=self._clock()
        )

    @staticmethod
    def _unlink_name(dir_fd: int, name: str) -> bool:
        try:
            os.unlink(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return False
        _fsync_dir(dir_fd)
        return True

    def delete(self, uri: str) -> DeletionReceipt:
        """Delete one output (final and partial) or reference; idempotent, never follows links."""
        is_output = isinstance(uri, str) and uri.startswith(f"private://{self._namespace}/outputs/")
        try:
            with self._root_fd() as root_fd:
                if is_output:
                    run_id, index = _parse_output(uri, self._namespace)
                    run_fd = self._run_dir(root_fd, run_id)
                    if run_fd is None:
                        return self._receipt("output", False)
                    try:
                        removed = [
                            self._unlink_name(run_fd, _final_name(index)),
                            self._unlink_name(run_fd, _partial_name(index)),
                        ]
                    finally:
                        os.close(run_fd)
                    return self._receipt("output", any(removed))
                name = _parse_reference(uri, self._namespace)
                refs_fd = self._subdir(root_fd, "references", create=False)
                if refs_fd is None:
                    return self._receipt("reference", False)
                try:
                    return self._receipt("reference", self._unlink_name(refs_fd, name))
                finally:
                    os.close(refs_fd)
        except OSError:
            raise StorageError("the deletion could not be completed") from None

    def withdraw(
        self, run_ids: Iterable[str], reference_uris: Iterable[str] = ()
    ) -> tuple[DeletionReceipt, ...]:
        """Withdraw identities' material: tombstone first, then delete everything. Idempotent.

        Tombstones are written (and fsynced) before any deletion and are never removed, so a
        withdrawn run can never be reserved or committed again, at any attempt index.
        Grant revocation by the private provider must precede this call (design note, §3.4).
        """
        runs = tuple(dict.fromkeys(run_ids))
        refs = tuple(dict.fromkeys(reference_uris))
        if not all(isinstance(r, str) and _RUN_ID_RE.fullmatch(r) for r in runs):
            raise StorageError("a run id is not valid")
        names = [_parse_reference(uri, self._namespace) for uri in refs]
        receipts: list[DeletionReceipt] = []
        try:
            with self._root_fd() as root_fd:
                for run_id in runs:
                    ledger_fd = self._run_ledger(root_fd, run_id, create=True)
                    if ledger_fd is None:  # pragma: no cover
                        raise StorageError("the attempt ledger is unavailable")
                    try:
                        self._touch_exclusive(ledger_fd, WITHDRAWN_FILE, 0o600)
                    finally:
                        os.close(ledger_fd)
                for run_id in runs:
                    receipts.append(self._receipt("run", self._delete_run(root_fd, run_id)))
                refs_fd = self._subdir(root_fd, "references", create=False)
                try:
                    for name in names:
                        removed = refs_fd is not None and self._unlink_name(refs_fd, name)
                        receipts.append(self._receipt("reference", removed))
                finally:
                    if refs_fd is not None:
                        os.close(refs_fd)
        except OSError:
            raise StorageError("the withdrawal could not be completed") from None
        return tuple(receipts)

    def _delete_run(self, root_fd: int, run_id: str) -> bool:
        outputs_fd = self._subdir(root_fd, "outputs", create=False)
        if outputs_fd is None:
            return False
        try:
            run_fd = self._subdir(outputs_fd, run_id, create=False)
            if run_fd is None:
                return False
            try:
                for name in os.listdir(run_fd):
                    try:
                        os.unlink(name, dir_fd=run_fd)
                    except IsADirectoryError:
                        raise StorageError("an unexpected directory is inside a run") from None
                _fsync_dir(run_fd)
            finally:
                os.close(run_fd)
            os.rmdir(run_id, dir_fd=outputs_fd)
            _fsync_dir(outputs_fd)
            return True
        finally:
            os.close(outputs_fd)

    def remaining(self, run_ids: Iterable[str], reference_uris: Iterable[str] = ()) -> int:
        """Count items still present, not tombstoned, or unreadable (0 means fully withdrawn)."""
        count = 0
        for run_id in dict.fromkeys(run_ids):
            if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
                raise StorageError("a run id is not valid")
            try:
                with self._root_fd() as root_fd:
                    if not self._is_withdrawn(root_fd, run_id):
                        count += 1
                    run_fd = self._run_dir(root_fd, run_id)
                    if run_fd is not None:
                        try:
                            count += max(1, len(os.listdir(run_fd)))
                        finally:
                            os.close(run_fd)
            except (OSError, StorageError):
                count += 1
        for uri in dict.fromkeys(reference_uris):
            name = _parse_reference(uri, self._namespace)
            try:
                with self._root_fd() as root_fd:
                    refs_fd = self._subdir(root_fd, "references", create=False)
                    if refs_fd is not None:
                        try:
                            count += int(_exists(refs_fd, name))
                        finally:
                            os.close(refs_fd)
            except (OSError, StorageError):
                count += 1
        return count

    def stale_reservations(self) -> tuple[str, ...]:
        """Opaque output URIs that still have a partial file (e.g. after a kill), for cleanup."""
        found: list[str] = []
        try:
            with self._root_fd() as root_fd:
                outputs_fd = self._subdir(root_fd, "outputs", create=False)
                if outputs_fd is None:
                    return ()
                try:
                    for run_id in sorted(os.listdir(outputs_fd)):
                        if not _RUN_ID_RE.fullmatch(run_id):
                            continue
                        run_fd = self._subdir(outputs_fd, run_id, create=False)
                        if run_fd is None:
                            continue
                        try:
                            for name in sorted(os.listdir(run_fd)):
                                match = re.fullmatch(r"\.attempt-([0-9]{2})\.partial\.mp4", name)
                                if match:
                                    found.append(
                                        f"private://{self._namespace}/outputs/{run_id}/"
                                        f"attempt-{match[1]}.mp4"
                                    )
                        finally:
                            os.close(run_fd)
                finally:
                    os.close(outputs_fd)
        except OSError:
            raise StorageError("the store could not be inspected") from None
        return tuple(found)

    def erase_store(self, *, revoked_grants_confirmed: bool) -> DeletionReceipt:
        """Irreversibly remove everything, including the ledger and its key, then seal the root.

        The ``ERASED`` sentinel is written first, so an interrupted erasure leaves a root that
        refuses all use. The flag is deliberate friction only: this code cannot see private grants,
        so the provider must have revoked every grant for this namespace beforehand.
        """
        if revoked_grants_confirmed is not True:
            raise StorageError("erasure requires confirmation that all grants were revoked")
        try:
            with self._root_fd(allow_erased=True) as root_fd:
                self._touch_exclusive(root_fd, ERASED_FILE, 0o600)
                self._remove_contents(root_fd)
        except OSError:
            raise StorageError("the erasure could not be completed") from None
        return DeletionReceipt(kind="store", outcome="erased", at=self._clock())

    def _remove_contents(self, dir_fd: int, *, top: bool = True) -> None:
        for name in os.listdir(dir_fd):
            if top and name == ERASED_FILE:
                continue
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
                try:
                    self._remove_contents(child, top=False)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=dir_fd)
            else:
                os.unlink(name, dir_fd=dir_fd)
        _fsync_dir(dir_fd)


__all__ = [
    "ERASED_FILE",
    "MAX_REFERENCE_BYTES",
    "DeletionReceipt",
    "LocalPrivateStore",
    "OutputStore",
    "ReferenceReader",
    "Reservation",
    "StorageError",
    "private_root_problems",
    "trusted_tree_problems",
    "withdrawal_run_ids",
]
