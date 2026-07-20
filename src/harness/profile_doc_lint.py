"""プロファイルの正本ドキュメントが入口から辿れるかの検査（profile_doc_lint）。

各プロファイル（`src/harness/<名>/profile.py` を持つディレクトリ）は、使い方の正本 `docs/<名>.md` を持ち、
その正本が doc 索引 `docs/README.md` から辿れる（リンクされている）こと。新しいプロファイルを足して索引へ
載せ忘れると（実際 stats がそうだった）、入口から到達できない正本が生まれ、索引が黙って古びる＝
「実装は正しいのに文書がそれを裏切る」形の陳腐化になる。これを verify で失敗させる（保証の (b)）。

プロファイル名の一覧は手書きせず `profiles.profile_names`（`profile.py` の走査）の 1 か所から引く＝
プロファイル追加時に検査対象へ自動で入る（一覧の二重管理をしない）。索引の照合はリンク先 `(名.md)` の
実在で見る（素の名前の部分一致だと `ds` が `odds.md` に当たる等の誤検知が起きるため、リンク形で確かめる）。
core の検査（プロファイル非依存）。stdlib と `harness.profiles` にだけ依存する。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm, profiles

_DOC_INDEX = "docs/README.md"


def _index_links_to(index_text: str, name: str) -> bool:
    """doc 索引が正本 `<名>.md` へリンクしているか（markdown リンク先で照合）。

    素の名前の部分一致だと `ds` が `odds.md` に当たるので、リンク先 `(…/名.md#…)` の形で見る。
    パス前置き（`docs/名.md`）・アンカー（`名.md#節`）も辿れる形として許す。
    """
    pattern = r"\((?:[^()]*/)?" + re.escape(name) + r"\.md(?:#[^()]*)?\)"
    return re.search(pattern, index_text) is not None


def run_checks(root: Path) -> list[pm.Problem]:
    """各プロファイルに正本 docs/<名>.md があり、doc 索引 docs/README.md から辿れるか検査する。欠落＝error。"""
    problems: list[pm.Problem] = []
    index = root / _DOC_INDEX
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    for name in profiles.profile_names(root):
        canon_rel = f"docs/{name}.md"
        if not (root / canon_rel).is_file():
            problems.append(
                pm.Problem(
                    "error",
                    f"プロファイル '{name}'（src/harness/{name}/）に使い方の正本 {canon_rel} が無い。"
                    f"各プロファイルは元コードを読まずに使えるよう docs/<名>.md を持つこと（profile_doc_lint）",
                )
            )
            continue
        if not _index_links_to(index_text, name):
            problems.append(
                pm.Problem(
                    "error",
                    f"{_DOC_INDEX} の索引が {canon_rel} を載せていない"
                    f"（プロファイル '{name}' を足したら索引に 1 行足す）。入口から各プロファイルの正本へ辿れる"
                    f"状態を保つ＝索引の黙った陳腐化を止める（profile_doc_lint）",
                )
            )
    return problems
