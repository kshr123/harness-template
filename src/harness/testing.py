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

# 検証のゲート（fast/standard/full）に永久に載らなくなる目印。skip/skipif/xfail はテストを動かさず、
# slow は checks.toml の全段階が `not slow` で除外する＝回す段階が無い（T-0202）。理由不要だと
# 「ISS 必須の skip/xfail」を迂回する抜け道になるため、slow も同格に reason への課題参照（ISS-<番号>）を
# 必須にする（AGENTS・ISS-0002）。
SKIP_MARKERS = frozenset({"skip", "skipif", "xfail", "slow"})

_ISS_REF_RE = re.compile(r"\bISS-\d+\b")


def unmarked(item_markers: Iterable[tuple[str, set[str]]]) -> list[str]:
    """各テストの (nodeid, 付いた目印の名前の集合) から、ピラミッドの目印が 1 つも無いものの nodeid を返す。"""
    pyramid = set(PYRAMID)
    return [nodeid for nodeid, names in item_markers if not (pyramid & names)]


def skips_without_iss(item_markers: Iterable[tuple[str, list[tuple[str, str]]]]) -> list[str]:
    """skip/skipif/xfail/slow の reason に課題参照（ISS-<番号>）が無いテストの nodeid を返す。

    入力は各テストの (nodeid, [(マーカー名, reason の文字列), ...])。reason が空（未指定）の対象マーカーも
    参照無しとして返す。SKIP_MARKERS 以外のマーカー（unit 等）は見ない。unmarked と同じ純粋関数
    （conftest の収集フックから呼ぶ・単体で確かめられる）。マーカーが関数装飾か、モジュール直書きの
    `pytestmark = pytest.mark.slow` かは問わない（pytest の `Item.iter_markers()` がどちらも同じ形で
    渡すため、呼び出し側の抽出だけで両方を拾える＝T-0202）。
    """
    bad: list[str] = []
    for nodeid, markers in item_markers:
        if any(name in SKIP_MARKERS and not _ISS_REF_RE.search(reason) for name, reason in markers):
            bad.append(nodeid)
    return bad


def markers_in_expr(expr: str) -> set[str]:
    """`pytest -m` の式（例 "e2e and not slow"）から、参照しているマーカー名の集合を取り出す。

    綴り違い・改名で門番が空回り（全 deselect→テスト0件なのに合格）するのを検査で防ぐために使う。
    """
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr) if t not in _MARKER_EXPR_KEYWORDS}
