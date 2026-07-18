"""保存物の由来書き（harness.provenance）の中核部品のテスト。

ds/models.py・agent/store.py に逐語で複製されていた 4 関数を 1 本化したもの（片方だけ直す退行を止める）。
ここで挙動を固定し、プロファイル側は薄い委譲だけを残す。
"""

from __future__ import annotations

import subprocess
from datetime import UTC
from pathlib import Path

import pytest

from harness import provenance, storage

pytestmark = pytest.mark.unit


def test_utcnow_is_timezone_aware_utc() -> None:
    now = provenance.utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)


def test_dependencies_reports_installed_and_skips_missing() -> None:
    # pytest は必ず入っている（このテスト自体が pytest で動く）。存在しない配布物は飛ばす（キーが出ない）。
    out = provenance.dependencies(["pytest", "definitely-not-a-real-distribution-xyz"])
    assert "pytest" in out and out["pytest"]
    assert "definitely-not-a-real-distribution-xyz" not in out


def test_dependencies_empty_iterable_is_empty_dict() -> None:
    assert provenance.dependencies([]) == {}


def test_git_provenance_none_outside_a_repo(tmp_path: Path) -> None:
    # git 管理下でない一時ディレクトリ＝来歴は取れないが例外にせず None（保存は止めない）。
    assert provenance.git_provenance(tmp_path) is None


def test_git_provenance_reads_commit_and_branch(tmp_path: Path) -> None:
    # 最小のリポを組んで、commit の短縮 hash・branch・dirty が構成どおり返ることを確かめる。
    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, encoding="utf-8")

    _git("init", "-b", "main")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "t")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git("add", "f.txt")
    _git("commit", "-m", "init")
    prov = provenance.git_provenance(tmp_path)
    assert prov is not None
    assert prov["branch"] == "main"
    assert isinstance(prov["commit"], str) and len(prov["commit"]) >= 4
    assert prov["dirty"] is False  # commit 直後・未追跡なし
    (tmp_path / "g.txt").write_text("y", encoding="utf-8")  # 未追跡ファイルを足す
    dirty_prov = provenance.git_provenance(tmp_path)
    assert dirty_prov is not None and dirty_prov["dirty"] is True  # untracked も dirty に数える


def test_lock_fingerprint_none_without_lock(tmp_path: Path) -> None:
    assert provenance.lock_fingerprint(tmp_path) is None


def test_lock_fingerprint_matches_storage_fingerprint(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text("dummy-lock-contents\n", encoding="utf-8")
    assert provenance.lock_fingerprint(tmp_path) == storage.fingerprint(lock)
