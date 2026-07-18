"""保存物に付ける由来書き（provenance）を集める policy-free な中核部品。

昇格の判定でも保存形式でもない＝どのプロファイルからも同じ形で使える（`harness.storage` と同じ層）。
`ds/models.py`・`agent/store.py` の保存の by-product として使う。両者にほぼ逐語で複製されていた
`_git_provenance`／`_dependencies`／`_lock_fingerprint`／`_utcnow` を 1 本化した（片方だけ直す退行を止める）。
プロファイル側は薄い委譲だけを残す（`_utcnow` は時刻を固定する monkeypatch の入口なので、
呼び手のモジュールにその 1 関数だけ残す）。

読むのは git コマンドの出力と配布物のメタデータだけ（認証情報・.env には触れない）。
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from harness import storage


def utcnow() -> datetime:
    """現在時刻（UTC）。プロファイル側の薄い委譲を通してテストが monkeypatch で固定する入口。"""
    return datetime.now(UTC)


def dependencies(tracked: Iterable[str]) -> dict[str, str]:
    """tracked の各配布物の版を集める（入っていないものは飛ばす）。記録のみ・照合は既定でしない。"""
    out: dict[str, str] = {}
    for dist in tracked:
        try:
            out[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            continue
    return out


def git_provenance(root: Path) -> dict[str, Any] | None:
    """git 来歴（短縮 commit・branch・作業木の dirty）。git リポでない/git 不在/失敗は None＝保存は止めない。"""

    def _run(*args: str) -> str:
        # encoding を明示する：省略するとロケール既定（Windows では cp932）で復号し、
        # 非 ASCII を含む git の出力（ブランチ名等）で UnicodeDecodeError になる。
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True, timeout=5
        )
        return proc.stdout.strip()

    try:
        commit = _run("rev-parse", "--short", "HEAD")
        branch = _run("rev-parse", "--abbrev-ref", "HEAD")
        # --untracked-files=normal を明示：利用者のグローバル設定 status.showUntrackedFiles に依らず、
        # 未追跡ファイルも dirty と数える（dirty の意味を環境非依存にする）。
        dirty = bool(_run("status", "--porcelain", "--untracked-files=normal"))
    except OSError, subprocess.SubprocessError, UnicodeDecodeError:
        # CalledProcessError（非 git リポ）・FileNotFoundError（git 不在）・TimeoutExpired を含む。
        # UnicodeDecodeError：git の出力が UTF-8 でない場合（来歴が取れないだけで、保存は続ける）。
        return None
    return {"commit": commit, "branch": branch, "dirty": dirty}


def lock_fingerprint(root: Path) -> str | None:
    """root 直下の uv.lock の sha256 指紋（どのロックで作ったかの印）。無ければ None。"""
    lock = root / "uv.lock"
    if not lock.is_file():
        return None
    return storage.fingerprint(lock)
