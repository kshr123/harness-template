"""テストのピラミッドの目印（unit/integration/e2e）を強制する部品。

conftest の collect フックがこれを使い、目印の無い「迷子テスト」（どの段階でも走らないテスト）を
失敗にする。純粋関数にして単体で確かめられるようにする（フック本体は薄い包み）。
段階×目印の対応と狙いは docs/method.md C 節・DESIGN.md（EP-06）C 節。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# ピラミッドの目印。各テストはこのいずれか 1 つを必ず持つ（slow は重いものに追加で貼るフラグ）。
PYRAMID = ("unit", "integration", "e2e")

# マーカー式（-m の値）で名前でない語＝論理演算子。名前の抽出時に除く。
_MARKER_EXPR_KEYWORDS = frozenset({"and", "or", "not"})


def unmarked(item_markers: Iterable[tuple[str, set[str]]]) -> list[str]:
    """各テストの (nodeid, 付いた目印の名前の集合) から、ピラミッドの目印が 1 つも無いものの nodeid を返す。"""
    pyramid = set(PYRAMID)
    return [nodeid for nodeid, names in item_markers if not (pyramid & names)]


def markers_in_expr(expr: str) -> set[str]:
    """`pytest -m` の式（例 "e2e and not slow"）から、参照しているマーカー名の集合を取り出す。

    綴り違い・改名で門番が空回り（全 deselect→テスト0件なのに合格）するのを検査で防ぐために使う。
    """
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr) if t not in _MARKER_EXPR_KEYWORDS}
