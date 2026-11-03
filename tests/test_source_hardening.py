"""Source-checkout and checkpoint-tree hardening (synthetic repositories and files only).

Two throwaway git repositories show that the inspector reports on the checkout it was given, not
on whatever ambient git state points elsewhere. No upstream code, weight or media is involved.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from frp.baseline.preflight import GitSourceInspector, WeightsVerificationError
from frp.baseline.preflight import verify_checkpoint_files as verify
from tests.baseline_support import make_checkpoint

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("git") is None, reason="needs Linux and git"
)

CLEAN_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        env=CLEAN_ENV,
    )
    return done.stdout.strip()


def make_repo(path: Path, content: str = "synthetic") -> str:
    path.mkdir()
    git(path, "init", "-q")
    (path / "module.py").write_text(content)
    (path / ".gitignore").write_text("*.pyc\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "synthetic")
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, str, Path, str]:
    a, b = tmp_path / "a", tmp_path / "b"
    return a, make_repo(a, "target"), b, make_repo(b, "other repository")


def test_a_clean_checkout_reports_its_own_commit(repos: tuple[Path, str, Path, str]) -> None:
    a, head_a, _b, _head_b = repos
    inspector = GitSourceInspector()
    assert inspector.head_commit(a) == head_a
    assert inspector.is_clean(a)


@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"])
def test_ambient_git_variables_cannot_redirect_the_inspection(
    repos: tuple[Path, str, Path, str], monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    a, head_a, b, head_b = repos
    value = {"GIT_DIR": b / ".git", "GIT_WORK_TREE": b, "GIT_INDEX_FILE": b / ".git" / "index"}
    monkeypatch.setenv(variable, str(value[variable]))
    assert GitSourceInspector().head_commit(a) == head_a != head_b


def test_config_injected_through_the_environment_is_ignored(
    repos: tuple[Path, str, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, _head_a, _b, _head_b = repos
    (a / "untracked.py").write_text("print('x')")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "status.showUntrackedFiles")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "no")
    assert not GitSourceInspector().is_clean(a)


def test_user_configuration_cannot_hide_untracked_files(
    repos: tuple[Path, str, Path, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a, *_ = repos
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[status]\n\tshowUntrackedFiles = no\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    (a / "untracked.py").write_text("print('x')")
    assert not GitSourceInspector().is_clean(a)


def test_a_git_file_redirecting_to_another_repository_is_refused(
    repos: tuple[Path, str, Path, str], tmp_path: Path
) -> None:
    _a, _head_a, b, _head_b = repos
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    (redirected / ".git").write_text(f"gitdir: {b / '.git'}\n")
    inspector = GitSourceInspector()
    assert inspector.head_commit(redirected) is None
    assert not inspector.is_clean(redirected)


def test_a_symlinked_git_directory_or_checkout_is_refused(
    repos: tuple[Path, str, Path, str], tmp_path: Path
) -> None:
    a, _head_a, b, _head_b = repos
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").symlink_to(b / ".git")
    link_to_checkout = tmp_path / "checkout-link"
    link_to_checkout.symlink_to(a)
    inspector = GitSourceInspector()
    assert inspector.head_commit(linked) is None
    assert inspector.head_commit(link_to_checkout) is None


def test_core_worktree_in_the_repository_config_cannot_redirect_the_work_tree(
    repos: tuple[Path, str, Path, str],
) -> None:
    a, _head_a, b, _head_b = repos
    git(a, "config", "core.worktree", str(b))  # b is clean; a gets a hidden modification below
    (a / "module.py").write_text("modified after the commit")
    assert not GitSourceInspector().is_clean(a)


def test_ignored_files_make_the_checkout_unclean(repos: tuple[Path, str, Path, str]) -> None:
    a, *_ = repos
    (a / "stale.pyc").write_bytes(b"synthetic bytecode")  # matched by the repository's .gitignore
    assert git(a, "status", "--porcelain") == ""  # plain `git status` would call this clean
    assert not GitSourceInspector().is_clean(a)


def test_excluded_files_make_the_checkout_unclean(repos: tuple[Path, str, Path, str]) -> None:
    a, *_ = repos
    (a / ".git" / "info" / "exclude").write_text("hidden.py\n")
    (a / "hidden.py").write_text("print('x')")
    assert not GitSourceInspector().is_clean(a)


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_index_flags_that_hide_modifications_are_refused(
    repos: tuple[Path, str, Path, str], flag: str
) -> None:
    a, *_ = repos
    git(a, "update-index", flag, "module.py")
    (a / "module.py").write_text("modified but hidden from git status")
    assert not GitSourceInspector().is_clean(a)


def test_tracked_modification_makes_the_checkout_unclean(
    repos: tuple[Path, str, Path, str],
) -> None:
    a, *_ = repos
    (a / "module.py").write_text("changed")
    assert not GitSourceInspector().is_clean(a)


def test_missing_checkout_reads_as_unverified(tmp_path: Path) -> None:
    inspector = GitSourceInspector()
    assert inspector.head_commit(tmp_path / "absent") is None
    assert not inspector.is_clean(tmp_path / "absent")


# -- checkpoint tree ---------------------------------------------------------------------------


def checkpoint(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "ckpt"
    root.mkdir()
    return root, make_checkpoint(root)


def test_a_trusted_checkpoint_tree_verifies(tmp_path: Path) -> None:
    root, expected = checkpoint(tmp_path)
    assert verify(root, expected, require_trusted_tree=True).files_sha256


def test_a_symlink_under_cache_is_refused_for_live_trees_only(tmp_path: Path) -> None:
    root, expected = checkpoint(tmp_path)
    (root / ".cache").mkdir()
    (root / ".cache" / "link").symlink_to(root / "config.json")
    assert verify(root, expected).files_sha256  # mock mode keeps the existing behaviour
    with pytest.raises(WeightsVerificationError):
        verify(root, expected, require_trusted_tree=True)


def test_a_group_writable_checkpoint_file_is_refused_before_hashing(tmp_path: Path) -> None:
    root, expected = checkpoint(tmp_path)
    (root / "config.json").chmod(0o664)
    with pytest.raises(WeightsVerificationError) as excinfo:
        verify(root, expected, require_trusted_tree=True)
    assert "writable" in "; ".join(excinfo.value.problems)
    assert "config.json" not in "; ".join(excinfo.value.problems)  # counts only, never names


def test_a_special_file_in_a_checkpoint_is_refused(tmp_path: Path) -> None:
    root, expected = checkpoint(tmp_path)
    os.mkfifo(root / "pipe")
    with pytest.raises(WeightsVerificationError):
        verify(root, expected, require_trusted_tree=True)


# -- runtime tripwires ---------------------------------------------------------------------------

OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


@pytest.mark.parametrize("name", ["IMAGEIO_FFMPEG_EXE", "LD_PRELOAD", "LD_AUDIT"])
def test_process_redirecting_variables_are_refused_by_name_only(name: str) -> None:
    from frp.baseline.wan21_runtime import runtime_environment_problems

    assert runtime_environment_problems(OFFLINE) == []
    problems = runtime_environment_problems({**OFFLINE, name: "/secret/value/path"})
    assert any(name in problem for problem in problems)
    assert "secret" not in " ".join(problems)


@pytest.mark.parametrize(
    ("isolated", "no_bytecode", "expected"),
    [(1, 1, 0), (0, 1, 1), (1, 0, 1), (0, 0, 2)],
)
def test_interpreter_must_be_isolated_and_write_no_bytecode(
    isolated: int, no_bytecode: int, expected: int
) -> None:
    from frp.baseline.wan21_runtime import interpreter_problems

    problems = interpreter_problems(isolated=isolated, dont_write_bytecode=no_bytecode)
    assert len(problems) == expected


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    (source / "wan").mkdir(parents=True)
    (source / "wan" / "image2video.py").write_text("# synthetic placeholder\n")
    return source


def test_a_symlink_or_writable_entry_in_the_source_tree_is_a_runtime_problem(
    tmp_path: Path,
) -> None:
    from frp.baseline.protocol import WAN21_SOURCE_COMMIT
    from frp.baseline.wan21_runtime import TorchWanRuntime
    from tests.baseline_support import FakeInspector

    source = _source(tmp_path)
    runtime = TorchWanRuntime(
        source_dir=source, source_inspector=FakeInspector(WAN21_SOURCE_COMMIT)
    )
    assert runtime._source_problems() == []

    (source / "wan" / "shadow.py").symlink_to(tmp_path / "elsewhere.py")
    problems = runtime._source_problems()
    assert any("symbolic link" in problem for problem in problems)

    (source / "wan" / "shadow.py").unlink()
    (source / "wan" / "image2video.py").chmod(0o666)
    assert any("writable" in problem for problem in runtime._source_problems())
