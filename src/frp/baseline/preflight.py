"""Local preflight checks that must pass before anything is loaded (CPU-testable, no ML imports).

* :func:`verify_checkpoint_files` hashes **every** file of a local checkpoint directory and
  compares the set and the SHA-256 digests with the separately approved expected manifest. Only a
  successful run issues a :class:`VerifiedCheckpoint`, which backends require in ``load``.
* :class:`GitSourceInspector` reads the commit of a local source checkout and whether it is clean.
* :func:`compute_environment_digest` turns a reported dependency set into a stable digest.
* :func:`network_blocked` and :func:`prohibited_modules_loaded` back the "no remote inference or
  image-to-text service" control. Blocking is best effort within the current process (it does not
  stop subprocesses or other threads' legitimate use), so it supplements, never replaces, an
  environment that has no route to those services.

Error messages are fixed strings with counts: they never contain file names, paths or hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

_CHUNK_BYTES: Final = 1 << 20
# HuggingFace `local_dir` downloads keep resume metadata here; it is not a model file.
_IGNORED_TOP_LEVEL: Final = frozenset({".cache"})
PROHIBITED_MODULES: Final = ("dashscope", "wan.utils.prompt_extend")
_GIT_TIMEOUT_SECONDS: Final = 30


class PreflightError(Exception):
    """Base class: ``problems`` are fixed descriptions without paths, names or hashes."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


class WeightsVerificationError(PreflightError):
    """Local checkpoint files are missing, unexpected, unreadable or have the wrong SHA-256."""


class RemoteAccessBlocked(RuntimeError):
    """A network connection or name lookup was attempted while remote access is blocked."""


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def weight_files_sha256(files: Mapping[str, str]) -> str:
    """Stable digest of a ``{relative path: sha256}`` file manifest."""
    canonical = json.dumps(dict(sorted(files.items())), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_ISSUER: Final = object()


@dataclass(frozen=True, slots=True)
class VerifiedCheckpoint:
    """Evidence that every file under ``root`` matched the approved manifest just before load.

    Only :func:`verify_checkpoint_files` should construct this; a backend's ``load`` accepts
    nothing else, so unverified weights cannot reach a loader through the executor.
    """

    root: Path = field(repr=False)
    files_sha256: str
    _issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise TypeError("VerifiedCheckpoint is issued only by verify_checkpoint_files")


def _list_files(root: Path) -> tuple[dict[str, Path], int]:
    found: dict[str, Path] = {}
    symlinks = 0
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(directory)
        if here == root:
            dirnames[:] = [d for d in dirnames if d not in _IGNORED_TOP_LEVEL]
        for name in list(dirnames):
            if (here / name).is_symlink():
                symlinks += 1
                dirnames.remove(name)
        for name in filenames:
            path = here / name
            if path.is_symlink():
                symlinks += 1
            else:
                found[path.relative_to(root).as_posix()] = path
    return found, symlinks


def verify_checkpoint_files(root: Path, expected: Mapping[str, str]) -> VerifiedCheckpoint:
    """Hash every file under ``root`` and require exactly the approved set with equal digests."""
    if not expected:
        raise WeightsVerificationError(["no expected file manifest was supplied"])
    if not root.is_dir() or root.is_symlink():
        raise WeightsVerificationError(["the local checkpoint directory is missing"])
    found, symlinks = _list_files(root)
    problems = []
    if symlinks:
        problems.append(f"{symlinks} symbolic link(s) found in the checkpoint directory")
    if missing := [name for name in expected if name not in found]:
        problems.append(f"{len(missing)} expected file(s) missing")
    if unexpected := [name for name in found if name not in expected]:
        problems.append(f"{len(unexpected)} unexpected file(s) present")
    mismatched = 0
    unreadable = 0
    for name, path in found.items():
        if name not in expected:
            continue
        try:
            actual = sha256_of_file(path)
        except OSError:
            unreadable += 1
            continue
        if actual != expected[name]:
            mismatched += 1
    if unreadable:
        problems.append(f"{unreadable} file(s) could not be read")
    if mismatched:
        problems.append(
            f"{mismatched} file(s) have a SHA-256 that differs from the approved manifest"
        )
    if problems:
        raise WeightsVerificationError(problems)
    return VerifiedCheckpoint(
        root=root, files_sha256=weight_files_sha256(expected), _issuer=_ISSUER
    )


class SourceInspector(Protocol):
    """Reports the commit of a local source checkout and whether it has local modifications."""

    def head_commit(self, path: Path) -> str | None: ...

    def is_clean(self, path: Path) -> bool: ...


class GitSourceInspector:
    """Reads a checkout with fixed ``git`` calls. Any failure reads as unverified."""

    def _git(self, path: Path, *args: str) -> str | None:
        git = shutil.which("git")
        if git is None or not path.is_dir():
            return None
        command = [git, "-C", str(path), "-c", "core.fsmonitor=false", *args]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed arguments, no shell
                command,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout.strip() if completed.returncode == 0 else None

    def head_commit(self, path: Path) -> str | None:
        return self._git(path, "rev-parse", "HEAD")

    def is_clean(self, path: Path) -> bool:
        # Untracked files count: extra .py files in a checkout could be imported.
        return self._git(path, "status", "--porcelain") == ""


def compute_environment_digest(
    distributions: Mapping[str, str], *, python_version: str, cuda_version: str | None
) -> str:
    """Stable digest of an installed-package set plus interpreter and CUDA versions.

    A *reported* environment, not an attestation: it is comparable to an approved digest, but
    this repository has frozen no environment and holds no approved digest.
    """
    canonical = json.dumps(
        {
            "python": python_version,
            "cuda": cuda_version,
            "distributions": {k.lower(): v for k, v in sorted(distributions.items())},
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prohibited_modules_loaded() -> list[str]:
    """Modules of the remote or image-to-text prompt-extension path that are already imported."""
    return [
        name
        for name in PROHIBITED_MODULES
        if name in sys.modules or any(m.startswith(name + ".") for m in sys.modules)
    ]


class NetworkGuard:
    """Counts the connection and lookup attempts blocked inside :func:`network_blocked`."""

    def __init__(self) -> None:
        self.blocked_calls = 0


@contextmanager
def network_blocked() -> Iterator[NetworkGuard]:
    """Refuse non-local-socket connections and name lookups for the duration of the block.

    Not thread-safe and process-wide while active; use only around backend calls.
    """
    guard = NetworkGuard()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    had_connect = "connect" in vars(socket.socket)
    had_connect_ex = "connect_ex" in vars(socket.socket)

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        guard.blocked_calls += 1
        raise RemoteAccessBlocked("network access is blocked during baseline execution")

    def connect(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX:
            return original_connect(self, address)
        return refuse()

    def connect_ex(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX:
            return original_connect_ex(self, address)
        return refuse()

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = refuse  # type: ignore[assignment]
    try:
        yield guard
    finally:
        socket.getaddrinfo = original_getaddrinfo
        for name, original, had in (
            ("connect", original_connect, had_connect),
            ("connect_ex", original_connect_ex, had_connect_ex),
        ):
            if had:
                setattr(socket.socket, name, original)
            else:
                delattr(socket.socket, name)
