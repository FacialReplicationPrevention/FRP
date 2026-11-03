"""Regression tripwires against accidentally shipping an activation path.

These AST and import checks are NOT a security proof: they catch the obvious ways a future change
could add a granting provider, an enable switch or a live-construction path, and nothing more. The
real controls are the denial defaults, the reviewed private integration contract and human gates.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from frp.baseline.authorisation import MAX_ATTEMPTS_PER_RUN
from frp.baseline.orchestrator import MAX_ATTEMPTS_LIMIT

SRC = Path(__file__).resolve().parents[1] / "src" / "frp"
FILES = sorted(SRC.rglob("*.py"))
NEVER_CONSTRUCTED = {
    "TorchWanRuntime",
    "Wan21UpstreamAdapter",
    "Wan21BaselineExecutor",
    "LocalPrivateStore",
}
DEFINING_MODULES = {
    "TorchWanRuntime": "wan21_runtime.py",
    "Wan21UpstreamAdapter": "wan21_adapter.py",
    "Wan21BaselineExecutor": "executor.py",
    "LocalPrivateStore": "private_storage.py",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_protocol(node: ast.ClassDef) -> bool:
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Subscript) and getattr(base.value, "id", "") == "Protocol")
        for base in node.bases
    )


def test_the_source_tree_is_found() -> None:
    assert len(FILES) > 20


def test_every_authorise_implementation_is_a_protocol_or_a_deny_all_returning_none() -> None:
    found = []
    for path in FILES:
        for cls in (n for n in ast.walk(_tree(path)) if isinstance(n, ast.ClassDef)):
            methods = [
                n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "authorise"
            ]
            if not methods:
                continue
            found.append(cls.name)
            if _is_protocol(cls):
                continue
            assert cls.name.startswith("DenyAll"), f"{cls.name} in {path.name} may grant"
            returns = [n for n in ast.walk(methods[0]) if isinstance(n, ast.Return)]
            assert returns
            assert all(isinstance(r.value, ast.Constant) and r.value.value is None for r in returns)
    assert {"DenyAllAuthorisation", "DenyAllReviewAccess"} <= set(found)


def test_no_live_component_is_constructed_in_the_shipped_source() -> None:
    for path in FILES:
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            assert name not in NEVER_CONSTRUCTED, f"{name}() is constructed in {path.name}"


def test_no_enable_switch_is_read_from_the_environment() -> None:
    for path in FILES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not node.value.startswith("FRP_"), f"FRP_* variable in {path.name}"


def test_the_cli_exposes_no_run_or_activation_command_or_option() -> None:
    import argparse

    from frp.cli import _build_parser

    names: set[str] = set()

    def walk(parser: argparse.ArgumentParser) -> None:
        for action in parser._actions:
            names.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                names.update(action.choices)
                for child in action.choices.values():
                    walk(child)

    walk(_build_parser())
    assert {"plan", "simulate", "baseline-plan", "provenance", "readiness"} <= names
    for name in names - {"--dry-run"}:
        for word in ("enable", "grant", "activate", "live", "run", "authorise", "unlock"):
            assert word not in name.lower(), f"CLI name {name!r} suggests an activation path"


@pytest.mark.parametrize("module", ["frp", "frp.cli", "frp.baseline", "frp.review"])
def test_importing_the_package_loads_no_ml_or_imaging_stack(module: str) -> None:
    code = (
        f"import sys, {module}\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in {'torch', 'PIL', 'wan', 'cv2',"
        " 'numpy', 'imageio', 'diffusers', 'transformers'}]\n"
        "print(','.join(sorted(bad)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""


def test_the_grant_attempt_cap_equals_the_orchestrator_cap() -> None:
    assert MAX_ATTEMPTS_PER_RUN == MAX_ATTEMPTS_LIMIT
