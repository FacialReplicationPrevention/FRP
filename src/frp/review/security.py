"""Local-only safety checks for the private review viewer (V1, V2, V4, V6, V8, V11).

Everything here is a *software* control on the reviewer's machine. None of it can stop a
screenshot, a screen recording, a shoulder-surfer or a compromised operating system; those are
residual risks documented in ``docs/private-review-viewer.md``.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

# Variables that indicate a hosted, remote or port-forwarded development environment (V2). Real,
# identifiable media must never be opened in such an environment; synthetic demos may be.
REMOTE_ENVIRONMENT_VARIABLES: Final = (
    "CODESPACES",
    "CODESPACE_NAME",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN",
    "REMOTE_CONTAINERS",
    "REMOTE_CONTAINERS_IPC",
    "VSCODE_REMOTE_CONTAINERS_SESSION",
    "VSCODE_AGENT_FOLDER",
    "SSH_CONNECTION",
    "SSH_CLIENT",
    "SSH_TTY",
    "GITPOD_WORKSPACE_ID",
    "CLOUD_SHELL",
    "COLAB_RELEASE_TAG",
    "COLAB_GPU",
    "KAGGLE_KERNEL_RUN_TYPE",
    "JUPYTERHUB_API_URL",
    "JPY_SESSION_NAME",
    "SAGEMAKER_INTERNAL_IMAGE_URI",
    "DATABRICKS_RUNTIME_VERSION",
    "GITHUB_ACTIONS",
    "CI",
)

LOOPBACK_HOST: Final = "127.0.0.1"
ALLOWED_HOST_NAMES: Final = frozenset({"127.0.0.1", "localhost", "[::1]"})

# Restrictive browser controls (V4, V5). Only the viewer's own origin may supply anything.
CONTENT_SECURITY_POLICY: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "object-src 'none'; media-src 'self'; font-src 'none'; worker-src 'none'; "
    "manifest-src 'none'"
)
SECURITY_HEADERS: Final = (
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("Cache-Control", "no-store, no-cache, must-revalidate, private, max-age=0"),
    ("Pragma", "no-cache"),
    ("Expires", "0"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cross-Origin-Embedder-Policy", "require-corp"),
    (
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), display-capture=(), clipboard-read=(), "
        "clipboard-write=(), usb=(), serial=(), bluetooth=(), payment=()",
    ),
    ("X-Robots-Tag", "noindex, nofollow, noarchive"),
)


def remote_environment_indicators(environ: Mapping[str, str] | None = None) -> list[str]:
    """Names (never values) of set variables that indicate a remote or hosted environment."""
    env = os.environ if environ is None else environ
    return [name for name in REMOTE_ENVIRONMENT_VARIABLES if env.get(name)]


def is_loopback_address(host: str) -> bool:
    """True only for a literal loopback IP address (names are not resolved)."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def inside_git_worktree(path: Path) -> bool:
    """True if ``path`` or any parent contains ``.git`` (risk of committing private material)."""
    resolved = path.resolve()
    return any((parent / ".git").exists() for parent in (resolved, *resolved.parents))


def group_or_world_accessible(path: Path) -> bool:
    """True on POSIX if group or others have any permission on ``path``."""
    if os.name != "posix":
        return False
    return bool(path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))


class OutboundNetworkBlocked(RuntimeError):
    """A non-loopback connection or a name lookup was attempted while the viewer was serving."""


class LoopbackGuard:
    """Counts the blocked outbound attempts inside :func:`loopback_only_network`."""

    def __init__(self) -> None:
        self.blocked_calls = 0


def _loopback_target(address: Any) -> bool:
    if isinstance(address, tuple) and address and isinstance(address[0], str):
        return is_loopback_address(address[0])
    return False


@contextmanager
def loopback_only_network() -> Iterator[LoopbackGuard]:
    """Refuse non-loopback connections and every name lookup in this process while active.

    In-process and best effort (it cannot see subprocesses or native extensions); the viewer
    makes no outbound calls by design, and this turns an accidental one into a failure.
    """
    guard = LoopbackGuard()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    had = {name: name in vars(socket.socket) for name in ("connect", "connect_ex")}

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        guard.blocked_calls += 1
        raise OutboundNetworkBlocked("outbound network access is blocked in the review viewer")

    def connect(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX or _loopback_target(address):
            return original_connect(self, address)
        return refuse()

    def connect_ex(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX or _loopback_target(address):
            return original_connect_ex(self, address)
        return refuse()

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(host, str) and is_loopback_address(host):
            return original_getaddrinfo(host, *args, **kwargs)
        return refuse()

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    socket.gethostbyname = refuse  # type: ignore[assignment]
    try:
        yield guard
    finally:
        socket.getaddrinfo = original_getaddrinfo
        socket.gethostbyname = original_gethostbyname
        for name, original in (("connect", original_connect), ("connect_ex", original_connect_ex)):
            if had[name]:
                setattr(socket.socket, name, original)
            else:
                delattr(socket.socket, name)


__all__ = [
    "ALLOWED_HOST_NAMES",
    "CONTENT_SECURITY_POLICY",
    "LOOPBACK_HOST",
    "REMOTE_ENVIRONMENT_VARIABLES",
    "SECURITY_HEADERS",
    "LoopbackGuard",
    "OutboundNetworkBlocked",
    "group_or_world_accessible",
    "inside_git_worktree",
    "is_loopback_address",
    "loopback_only_network",
    "remote_environment_indicators",
]
