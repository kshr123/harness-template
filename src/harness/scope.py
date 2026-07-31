"""変更に応じて回す検査を絞る（編集ループ用の"参考"実行）の計画づくり。

`uv run check --scope diff` が使う。git 差分から「何を回すか」を決める。**これは advisory（回さない経路がありうる）
＝done の証拠にしない**。権威ある完全実行は `uv run verify`（と CI）で、そこは常に全部走る
（背骨：完了＝検証にすべて成功）。

スコープの健全性は「迷ったら全実行（fail-closed の過近似）」で守る：分類できないファイル・検査インフラ・中核の
変更は全実行に落とす。許すもの（＝絞ってよい変更の種類）だけを正の形で列挙し、列挙外は既定で全実行になる。
影響のグラフは新設しない＝既存の単一台帳 `Profile.test_globs`（収集除外・mypy 除外と同じ出どころ）を使う。
"""

from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path

from harness import profiles

# 変更されたら「全実行」に落とす検査インフラ／中核（スコープの土台を触ったら、スコープでは判断できない）。
_FORCE_FULL_FILES: frozenset[str] = frozenset(
    {
        "checks.toml",
        "pyproject.toml",
        "uv.lock",
        "tests/conftest.py",
        "tests/_headless.py",
        "src/harness/checks.py",
        "src/harness/scope.py",
        "src/harness/profiles.py",
        "src/harness/testing.py",
        ".harness/config.toml",
    }
)
_FORCE_FULL_PREFIXES: tuple[str, ...] = (".github/",)
# 散文だけの変更＝不変条件のみでよい置き場（コード・型・テストは回さない）。
_PROSE_PREFIXES: tuple[str, ...] = ("docs/", ".claude/skills/", "templates/", "work/", "issues/")


@dataclass(frozen=True)
class Plan:
    """`--scope diff` の実行計画。`full=True` なら verify と同じ全実行に落とす。"""

    full: bool
    run_ruff: bool
    run_mypy: bool
    pytest_files: tuple[str, ...]
    reason: str


def _git_lines(root: Path, *args: str) -> list[str] | None:
    """git を 1 回呼んで標準出力の行を返す（失敗・git 無しは None）。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=15, check=False
        )
    except OSError:
        return None
    return proc.stdout.splitlines() if proc.returncode == 0 else None


def changed_files(root: Path) -> list[str] | None:
    """origin/main との差分 ＋ 未ステージ ＋ 未追跡（リポ相対・posix）。差分を決められなければ None（＝全実行）。"""
    base = _git_lines(root, "merge-base", "origin/main", "HEAD")
    if base is None or not base:
        return None  # origin/main が無い・git でない＝安全側（全実行）に倒す
    out: set[str] = set()
    for args in (
        ("diff", "--name-only", base[0].strip()),  # マージ基点からの差分（改名は両側が出る）
        ("diff", "--name-only"),  # 未ステージ
        ("ls-files", "--others", "--exclude-standard"),  # 未追跡
    ):
        lines = _git_lines(root, *args)
        if lines is None:
            return None
        out.update(lines)
    return sorted(f for f in out if f)


def _is_core_src(f: str) -> bool:
    """`src/harness/*.py`（直下・非再帰）＝中核。全プロファイルが import するので全実行に落とす。"""
    return f.startswith("src/harness/") and f.count("/") == 2 and f.endswith(".py")


def _force_full(f: str) -> bool:
    return f in _FORCE_FULL_FILES or f.startswith(_FORCE_FULL_PREFIXES) or _is_core_src(f)


def _is_prose(f: str) -> bool:
    return f.endswith(".md") or f.startswith(_PROSE_PREFIXES)


def _owning_profile(f: str, profs: list[profiles.Profile]) -> str | None:
    """f を所有するプロファイル名（`src/harness/<name>/**` か、その `test_globs` に当たるテスト）。"""
    for prof in profs:
        if f.startswith(f"src/harness/{prof.name}/"):
            return prof.name
    if f.startswith("tests/") and f.endswith(".py"):
        name = f.rsplit("/", 1)[-1]
        for prof in profs:
            if any(fnmatch.fnmatchcase(name, g) for g in prof.test_globs):
                return prof.name
    return None


def build_plan(root: Path) -> Plan:
    """git 差分から実行計画を決める（分類できない・検査インフラ・中核は全実行＝fail-closed）。"""
    changed = changed_files(root)
    if changed is None:
        return Plan(True, True, True, (), "差分を決められない（git/origin なし）＝全実行")
    return route(root, changed)


def route(root: Path, changed: list[str]) -> Plan:
    """変更ファイルの一覧から実行計画を決める（git に依存しない純粋な振り分け＝テストしやすい）。"""
    if not changed:
        return Plan(False, False, False, (), "差分なし＝不変条件のみ")

    profs = list(profiles.discover_profiles(root).values())
    run_ruff = run_mypy = False
    pytest_files: set[str] = set()
    touched_profiles: set[str] = set()
    for f in changed:
        if _force_full(f):
            return Plan(True, True, True, (), f"検査インフラ／中核の変更（{f}）＝全実行")
        if _is_prose(f):
            continue  # 散文＝不変条件のみ（下で回すコマンドに寄与しない）
        owner = _owning_profile(f, profs)
        if owner is not None:
            touched_profiles.add(owner)
            run_ruff = run_mypy = True
            continue
        if f.startswith("tests/") and f.endswith(".py"):  # プロファイル非所有のテスト（中核テスト）
            pytest_files.add(f)
            run_ruff = run_mypy = True
            continue
        # ここに来る非散文の変更（分類できない src の .py・その他）は安全側で全実行に落とす。
        return Plan(True, True, True, (), f"分類できない変更（{f}）＝全実行")

    for prof in profs:
        if prof.name in touched_profiles:
            for glob in prof.test_globs:
                pytest_files.update(p.relative_to(root).as_posix() for p in (root / "tests").glob(glob))

    if not (run_ruff or run_mypy or pytest_files):
        return Plan(False, False, False, (), "散文のみの変更＝不変条件のみ")
    return Plan(
        False, run_ruff, run_mypy, tuple(sorted(pytest_files)), f"スコープ実行（テスト {len(pytest_files)} 本）"
    )
