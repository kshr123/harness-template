"""複製後の初期化（init-project）。

fork した案件（`git clone` した複製）を白紙化し、`uv run verify` が緑になる出発点に戻す。
`docs/template-copy.md` の「消す・作り直す」の手作業（読み忘れ・やり忘れという発生源を持つ）を
実行可能な 1 コマンドに集約する。触るのは**案件領域だけ**（`work/`・`issues/`・
`docs/requirements/`・`docs/charter.md`・`docs/learnings.md`・`data/`・`.harness/config.toml` の
`profiles`）。本体領域（`src/harness/`・`tests/`・`.claude/skills/`・`templates/`・本体の docs・
`AGENTS.md` 等）には触れない。境界の正本は `docs/template-copy.md`。

安全装置：破壊的操作なので CLI 側で `--force` か確認プロンプトを必須にする。さらに、まだ fork して
いない状態（`upstream` リモートが無い＝テンプレート本体そのもの、または fork 設定前）で走らせたら
**拒否**する（誤爆で本体を初期化しない）。判定の芯（純関数）はこのモジュールに置き、git の副作用
（リモート一覧の取得）だけを `list_remotes` に閉じ込める。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# 初期化後に置く雛形（案件が最初に書き換える出発点）。
_CHARTER_TEMPLATE = """\
---
project: TODO
status: active
owner: TODO
---
# プロジェクト憲章：TODO（この案件は何のためにあるか）

この文書は案件の立ち上げ文書（プロジェクト憲章）。この案件が何のためにあり、何をやり・何をやらず、
どうなったら成功かを、着手前に 1 枚で合意するために書く。fork 直後に `uv run init-project` が
この雛形に戻す（複製手順は docs/template-copy.md）。

## 目的（この案件は何のために・誰の何を解決するか）
TODO

## スコープ（やること／やらないこと）
- やる：TODO
- やらない：TODO

## 成功の定義（どうなったら成功か。確かめられる形で）
TODO
"""

_REQUIREMENT_TEMPLATE = """\
---
id: REQ-001
kind: functional
status: draft
satisfies: []
---
# REQ-001：TODO（この案件が満たす最初の要件）

## 内容（何を満たすか）
TODO

## 受け入れ基準（どうなったら満たすか。確かめられる形で書く）
- [ ] TODO
"""

_LEARNINGS_TEMPLATE = """\
# 気づきの記録（learnings）

作業中の気づき（工夫・使いにくかった点）を 1 件＝1 項目で書き足す（書式・扱いは docs/method.md C 節、
振り返りの手順は harvest スキル）。ルール化して正本が AGENTS/検査へ移ったら、次の見直しで消す。
"""


# 案件領域の「根」の正本（fork で白紙化され、`git merge upstream/main` の復旧レシピが fork 側へ戻す集合）。
# これ 1 か所が正本＝(1) scrub が触るパスはすべてこの根の下（`test_init_project` が検査）、(2) merge 復旧の
# AREAS はこの根を漏れなく覆う（`test_template_copy` が検査）。新しい案件領域の根を足すときはここに 1 行足す。
# 各要素はディレクトリ・ファイル・glob のいずれか（`docs/structure-review-*.md` のような glob も可）。
CASE_AREA_ROOTS: tuple[str, ...] = (
    "work",
    "issues",
    "docs/requirements",
    "docs/demands",
    "docs/wbs.yaml",
    "docs/charter.md",
    "docs/learnings.md",
    "docs/structure-review-*.md",
    "data",
    ".harness/config.toml",
)

# scrub が `profiles` を書き換える設定ファイル（案件領域）。set_profiles と declared_scrub_targets が共有する 1 か所。
_CONFIG_FILE = ".harness/config.toml"


@dataclass
class ScrubResult:
    """初期化で行った操作の記録（何を消し・何を雛形に戻し・どの profiles にしたか）。"""

    removed: list[str] = field(default_factory=list)  # 消したパス（root からの相対）
    reset: list[str] = field(default_factory=list)  # 雛形に戻したパス（root からの相対）
    profiles: list[str] = field(default_factory=list)  # 設定した profiles


def list_remotes(root: Path) -> set[str]:
    """`git remote` の集合を返す。git が無い・リポジトリでない・失敗したときは空集合。

    副作用（git 呼び出し）はここだけに閉じ込め、判定は `is_forked`（純関数）へ渡す。
    ネットワークは使わない（ローカルの設定を読むだけ）。
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except OSError:
        return set()
    except subprocess.SubprocessError:
        return set()
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def is_forked(remotes: set[str]) -> bool:
    """fork 済み（`upstream` リモートがある）か。

    T-0193 の fork 手順は `git clone` → `git remote rename origin upstream` →
    `git remote add origin <案件リモート>`。よって案件（fork）では `upstream` が本体を指す。
    テンプレート本体（まだ fork していない）には `upstream` が無いので、これで両者を機械的に分けられる。
    """
    return "upstream" in remotes


def blocking_reason(*, forked: bool) -> str | None:
    """初期化を拒否すべき理由（無ければ None）。まだ fork していない状態では拒否する（本体の誤爆防止）。"""
    if not forked:
        return (
            "拒否：この作業ツリーには `upstream` リモートが無い（テンプレート本体そのもの、または fork の "
            "設定前）。init-project は fork した案件を白紙化するコマンドで、本体を初期化しないための安全装置。"
            "先に fork の設定をすること（git clone <template> → git remote rename origin upstream → "
            "git remote add origin <案件リモート>。詳細は docs/template-copy.md）"
        )
    return None


def set_profiles(root: Path, profiles: list[str]) -> None:
    """`.harness/config.toml` の `profiles = [...]` 行を書き換える（コメント・他設定は保つ）。

    非 DS 案件は `[]`。行が無ければ末尾に足す。値は TOML の文字列配列として書く。
    """
    path = root / _CONFIG_FILE
    rendered = "profiles = [" + ", ".join(f'"{p}"' for p in profiles) + "]"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(r"(?m)^profiles\s*=.*$", rendered, text, count=1)
    if count == 0:
        new_text = text.rstrip("\n") + "\n" + rendered + "\n"
    path.write_text(new_text, encoding="utf-8")


def _remove_glob(root: Path, rel_dir: str, pattern: str, result: ScrubResult) -> None:
    """`rel_dir` 直下の `pattern` に一致する項目（ファイル・ディレクトリ）を消して記録する。"""
    base = root / rel_dir
    if not base.is_dir():
        return
    for path in sorted(base.glob(pattern)):
        _remove_path(path, root, result)


def _remove_path(path: Path, root: Path, result: ScrubResult) -> None:
    rel = path.relative_to(root).as_posix()
    if path.is_dir():
        _rmtree(path)
    else:
        path.unlink()
    result.removed.append(rel)


def _rmtree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    path.rmdir()


def _reset_file(root: Path, rel: str, content: str, result: ScrubResult) -> None:
    """ファイルを雛形の内容で上書きし、記録する（親が無ければ作る）。"""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    result.reset.append(rel)


# 白紙化の宣言（案件領域だけ）。対象を**データとして 1 か所に**置く＝scrub の効果でなく宣言そのものを検査でき、
# 対象集合が実装の申告に依存しない（`test_init_project` が各対象が CASE_AREA_ROOTS の下にあることを静的に検査）。
_REMOVE_GLOBS: tuple[str, ...] = (
    "work/EP-*",
    "work/T-*",
    "work/INV-*",
    "work/E-*",
    "issues/ISS-*",
    "docs/requirements/REQ-*",
    "docs/demands/DEM-*",
    "docs/wbs.yaml",
    "docs/structure-review-*.md",
)
_REMOVE_DIRS: tuple[str, ...] = ("data",)
_RESET_FILES: tuple[tuple[str, str], ...] = (
    ("docs/requirements/REQ-001.md", _REQUIREMENT_TEMPLATE),
    ("docs/charter.md", _CHARTER_TEMPLATE),
    ("docs/learnings.md", _LEARNINGS_TEMPLATE),
)


def declared_scrub_targets() -> tuple[str, ...]:
    """scrub が触る対象の宣言（消す glob／ディレクトリ・戻すファイル・設定を書く config）。効果でなく宣言を検査する用。

    scrub が実際に触るパスをすべて列挙する（`_CONFIG_FILE` は set_profiles が書く先）＝
    CASE_AREA_ROOTS の docstring「触るパスはすべて根の下」を厳密に真にする。
    """
    return (*_REMOVE_GLOBS, *_REMOVE_DIRS, *(rel for rel, _ in _RESET_FILES), _CONFIG_FILE)


def scrub(root: Path, profiles: list[str]) -> ScrubResult:
    """案件領域を初期化する（本体領域には触れない）。何度呼んでも同じ状態になる（べき等）。

    対象は `_REMOVE_GLOBS`・`_REMOVE_DIRS`・`_RESET_FILES` の宣言（各対象は `CASE_AREA_ROOTS` の下）：
    - `work/`：前案件の作業単位（`EP-*`・`T-*`・`INV-*`・`E-*`）を消す。
    - `issues/`：前案件の課題（`ISS-*`）を消す。
    - `docs/requirements/`：前案件の要件（`REQ-*`）を消し、雛形 `REQ-001.md` を置く。
    - `docs/demands/`：前案件の要求（`DEM-*`）を消す。
    - `docs/wbs.yaml`：前案件の顧客向け WBS の上書き（節構成・カレンダー・手動行）を消す。
    - `docs/charter.md`・`docs/learnings.md`：雛形に戻す。
    - `docs/structure-review-*.md`：基盤のレビュー記録（履歴）を消す。
    - `data/`：生成物（実データ・保存済みモデル）を消す。
    - `.harness/config.toml`：`profiles` を設定する。
    """
    result = ScrubResult(profiles=list(profiles))

    for g in _REMOVE_GLOBS:
        rel_dir, pattern = g.rsplit("/", 1)
        _remove_glob(root, rel_dir, pattern, result)
    for d in _REMOVE_DIRS:
        # 生成物（実体）を消す。ディレクトリごと消してよい（追跡対象は .gitignore で除外＝生成物のみ）。
        p = root / d
        if p.is_dir():
            _remove_path(p, root, result)
    for rel, content in _RESET_FILES:
        _reset_file(root, rel, content, result)

    set_profiles(root, profiles)
    return result
