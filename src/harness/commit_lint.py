"""コミットメッセージの作業単位 ID 検査（commit-msg フックの実体・来歴を機械で守る）。

全コミットの冒頭行が `work/` に実在する作業単位 ID（例 `EP-20 T-0101：…`）を含むことを検査する。
「何をどの根拠で変えたか」の来歴を、慣習（自制頼み）から機械検査へ一段強くする（T-0101）。

- **ID の正本は `pm.load_tree` の木だけ**＝ここで新しい ID 一覧を作らない（二重管理を作らないの思想）。
- ID らしき文字列（例 `T-9999`）があっても木に実在しなければ error（打ち間違い・架空 ID を止める）。
- 免除は接頭辞の明示リスト（`_EXEMPT_PREFIXES`・理由必須）だけ＝fail closed（coverage_lint の `_EXEMPT` と同型）。
- import は stdlib＋`harness.pm` のみ（core の検査・プロファイル非依存）。

有効化は `pre-commit install --hook-type commit-msg`（既定の `pre-commit install` では commit-msg
ステージは入らず素通りになる）。配線の常在検査は tests/test_commit_lint.py（T-0100 の型）。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 作業単位 ID の形（pm.UNIT_FILE と同じ種別集合）。re.ASCII で \b・\d を ASCII に限定する
# （日本語文字は非単語扱い＝`T-0101：…` の直後が句読点でなくても境界が成立し、全角数字は拾わない）。
_ID_LIKE = re.compile(r"\b(?:EP|T|INV|E)-\d+\b", re.ASCII)

# 免除リスト：ツール生成コミットの定型接頭辞だけ（接頭辞 → なぜ免除かの理由。空は不可＝fail closed）。
# ここに無い形はすべて ID 必須。広げる＝ポリシー変更なので tests/test_commit_lint.py の
# EXEMPT_PREFIX_POLICY と同時に更新する（黙って免除を広げない）。
_EXEMPT_PREFIXES: dict[str, str] = {
    # 末尾スペース／`!␣`＝git が実際に生成する形に締める。手書きの `Merged …`・`Reverting …`
    # （スペース無し）は免除に該当させず、ID 検査を素通りできないようにする（fail closed）。
    "Merge ": "git merge / pull が生成する定型メッセージ。人が書式を制御できず、来歴は両親コミットが持つ。",
    'Revert "': 'git revert が生成する定型メッセージ（`Revert "…"`）。取り消し対象が来歴（元の ID）を持つ。',
    "fixup! ": "git commit --fixup の定型接頭辞。rebase --autosquash で対象コミットへ吸収される一時コミット。",
    "squash! ": "git commit --squash の定型接頭辞。同上（歴史に残らない一時コミット）。",
}

_FORMAT_HINT = "冒頭行に work/ に実在する作業単位 ID を含めること（例 `EP-20 T-0101：変更の要約`）"


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す（coverage_lint._validated_exempt と同型）。"""
    for prefix, reason in _EXEMPT_PREFIXES.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT_PREFIXES[{prefix!r}] の理由が空。免除には人が読める理由が必須（commit_lint）")
    return _EXEMPT_PREFIXES


def known_ids(root: Path) -> set[str]:
    """work/ の木に実在する作業単位 ID を集める（正本＝pm.load_tree。木の構造の問題は task-lint の領分）。"""
    nodes, _problems = pm.load_tree(root)
    ids: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        ids.add(node.item.id)
        stack.extend(node.children)
    return ids


def check_message(message: str, ids: set[str]) -> list[pm.Problem]:
    """純関数：メッセージ冒頭行に実在 ID があるかを判定する（root 非依存＝テストしやすい判定の芯）。"""
    exempt = _validated_exempt()
    # git の cleanup 相当：コメント行（# 始まり）と空行を除いた最初の行を「冒頭行」とする
    # （エディタ経由のメッセージファイルはコメント・先頭空行を含みうる）。
    first = next((ln.strip() for ln in message.splitlines() if ln.strip() and not ln.startswith("#")), "")
    if not first:
        return []  # 空メッセージは git 側が別途拒否する（ここで二重に咎めない）
    if any(first.startswith(prefix) for prefix in exempt):
        return []  # ツール生成コミット（免除の理由は _EXEMPT_PREFIXES に明記）
    found = list(dict.fromkeys(_ID_LIKE.findall(first)))  # 出現順を保って重複を除く
    if not found:
        return [
            pm.Problem(
                "error",
                f"コミットメッセージに作業単位 ID が無い。{_FORMAT_HINT}。"
                f"免除（ツール生成コミットの接頭辞のみ）: {', '.join(p.strip() for p in exempt)}",
            )
        ]
    return [
        pm.Problem(
            "error",
            f"コミットメッセージの ID '{token}' が work/ に実在しない（打ち間違い・架空 ID を止める）。{_FORMAT_HINT}",
        )
        for token in found
        if token not in ids
    ]


def lint_message(root: Path, message: str) -> list[pm.Problem]:
    """メッセージ冒頭行に、pm.load_tree(root) から得た実在 ID が 1 つ以上含まれるかを検査する。"""
    return check_message(message, known_ids(root))
