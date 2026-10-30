"""Local hash, source, environment and network-guard preflight (synthetic files only)."""

from __future__ import annotations

import _socket
import socket
from pathlib import Path

import pytest

from frp.baseline.preflight import (
    PROHIBITED_MODULES,
    RemoteAccessBlocked,
    VerifiedCheckpoint,
    WeightsVerificationError,
    compute_environment_digest,
    network_blocked,
    prohibited_modules_loaded,
    verify_checkpoint_files,
    weight_files_sha256,
)
from tests.baseline_support import make_checkpoint


def test_matching_files_verify(tmp_path: Path) -> None:
    expected = make_checkpoint(tmp_path)
    verified = verify_checkpoint_files(tmp_path, expected)
    assert verified.files_sha256 == weight_files_sha256(expected)
    assert str(tmp_path) not in repr(verified)


def test_verified_checkpoint_cannot_be_forged(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        VerifiedCheckpoint(root=tmp_path, files_sha256="a" * 64, _issuer=object())


@pytest.mark.parametrize(
    "case", ["changed", "missing", "extra", "symlink", "no_manifest", "no_dir"]
)
def test_discrepancies_abort_without_leaking_names(tmp_path: Path, case: str) -> None:
    root = tmp_path / "ckpt"
    root.mkdir()
    expected = make_checkpoint(root)
    if case == "changed":
        (root / "weights/a.bin").write_bytes(b"tampered")
    elif case == "missing":
        (root / "weights/b.bin").unlink()
    elif case == "extra":
        (root / "unexpected-model.pth").write_bytes(b"x")
    elif case == "symlink":
        (root / "link.bin").symlink_to(root / "config.json")
    elif case == "no_manifest":
        expected = {}
    elif case == "no_dir":
        root = tmp_path / "absent"
    with pytest.raises(WeightsVerificationError) as excinfo:
        verify_checkpoint_files(root, expected)
    text = str(excinfo.value)
    assert "a.bin" not in text
    assert "unexpected-model" not in text
    assert str(tmp_path) not in text


def test_hub_cache_metadata_dir_is_ignored(tmp_path: Path) -> None:
    expected = make_checkpoint(tmp_path)
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "resume.json").write_bytes(b"{}")
    verify_checkpoint_files(tmp_path, expected)


def test_environment_digest_is_stable_and_sensitive() -> None:
    a = compute_environment_digest({"torch": "2.4.0"}, python_version="3.11", cuda_version="12.1")
    b = compute_environment_digest({"Torch": "2.4.0"}, python_version="3.11", cuda_version="12.1")
    c = compute_environment_digest({"torch": "2.4.1"}, python_version="3.11", cuda_version="12.1")
    assert a == b != c


def test_network_guard_blocks_connections_and_lookups_and_restores() -> None:
    original = socket.getaddrinfo
    with network_blocked() as guard:
        with pytest.raises(RemoteAccessBlocked):
            socket.getaddrinfo("example.invalid", 80)
        with pytest.raises(RemoteAccessBlocked):
            socket.create_connection(("192.0.2.1", 80), timeout=0.1)
    assert guard.blocked_calls == 2
    assert socket.getaddrinfo is original
    assert socket.socket.connect is _socket.socket.connect


def test_prohibited_module_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    assert prohibited_modules_loaded() == []
    monkeypatch.setitem(sys.modules, "dashscope", types.ModuleType("dashscope"))
    assert prohibited_modules_loaded() == ["dashscope"]
    assert "wan.utils.prompt_extend" in PROHIBITED_MODULES
