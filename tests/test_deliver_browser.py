"""実ブラウザ（headless Chrome）での受け入れ実測。

ここでしか確かめられないのは runtime 挙動＝イベントを発火させた後に class・textContent が実際にどう変わるか。
文字列パースだけだと、依存の逆写像や折りたたみの DOM 操作を壊す変異が緑のまま通る。Chrome が無ければ skip する
（`_headless.chrome_path`）。データ側の検査（`test_deliver_geometry` の data-deps）と JS 構文検査
（`test_deliver_script`）は Chrome 無しでも常に回る。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from _headless import dump_dom  # tests/ は sys.path に載る（prepend import）＝素の名前で取り込める

from harness.deliver import render
from harness.deliver import wbs as wbs_mod
from harness.deliver.overlay import Overlay

# browser マーカー＝実 Chrome を起動する 3 本。既定の `uv run verify` からは除外（checks.toml が
# `not browser`）し、描画を触るタスクでは `check --scope diff` が deliver 変更として走らせ、merge 前に
# CI（.github/workflows/ci.yaml の verify ジョブ）で必須実行する。幾何（座標）は Python で計算され
# `tests/test_deliver_geometry.py`（unit）が毎回ブラウザ無しで検証済み＝ここが守るのは JS/DOM の振る舞いだけ。
pytestmark = [pytest.mark.integration, pytest.mark.browser]

TODAY = date(2026, 8, 20)


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _tree(root: Path) -> None:
    """EP-90（親）の下に A→B の依存（B が A に依存）と、無関係な C を置く。"""
    ep = root / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        ep / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        ep / "T-9002-b.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "todo",
            "start": "2026-08-10",
            "due": "2026-08-12",
            "depends_on": ["T-9001"],
        },
    )
    _write(
        ep / "T-9003-c.md",
        {"id": "T-9003", "kind": "task", "status": "todo", "start": "2026-08-14", "due": "2026-08-18"},
    )


def _html(root: Path) -> str:
    return render.render_html(wbs_mod.build(root, today=TODAY, overlay=Overlay()))


def _attr(dom: str, name: str) -> str:
    """dump-dom の body に書き込んだ結果属性を読む（見つからなければ AssertionError で落とす）。"""
    m = re.search(rf'data-{name}="([^"]*)"', dom)
    assert m is not None, f"data-{name} が DOM に無い（スクリプトが走っていない）: {dom[:200]}"
    return m.group(1)


def test_hovering_a_successor_highlights_its_predecessor(tmp_path: Path) -> None:
    """B（後続）にかざすと A（先行）に dep-hi が付き、無関係な C には付かない（先行方向の実測）。"""
    _tree(tmp_path)
    inject = (
        "document.querySelector('tr[data-ref=\"T-9002\"]').dispatchEvent(new Event('mouseenter'));"
        "function hi(r){return document.querySelector('tr[data-ref=\"'+r+'\"]').classList.contains('dep-hi');}"
        "document.body.setAttribute('data-pred', hi('T-9001'));"
        "document.body.setAttribute('data-unrel', hi('T-9003'));"
    )
    dom = dump_dom(_html(tmp_path), inject=inject)
    assert _attr(dom, "pred") == "true"  # 先行 A が光る
    assert _attr(dom, "unrel") == "false"  # 無関係 C は光らない


def test_hovering_a_predecessor_highlights_its_successor(tmp_path: Path) -> None:
    """A（先行）にかざすと B（後続）に dep-hi が付く（逆写像 succ の実測＝data-deps だけでは確かめられない）。"""
    _tree(tmp_path)
    inject = (
        "document.querySelector('tr[data-ref=\"T-9001\"]').dispatchEvent(new Event('mouseenter'));"
        "document.body.setAttribute('data-succ',"
        " document.querySelector('tr[data-ref=\"T-9002\"]').classList.contains('dep-hi'));"
    )
    dom = dump_dom(_html(tmp_path), inject=inject)
    assert _attr(dom, "succ") == "true"


def test_folding_all_does_not_write_a_triangle_into_leaf_rows(tmp_path: Path) -> None:
    """「全部たたむ」を押しても、末端行の空の span.tw に三角（▸）が書き込まれない（親のボタンだけが畳む）。"""
    _tree(tmp_path)
    inject = (
        "document.getElementById('fold').click();"
        "var leaf=document.querySelector('tr[data-code=\"1.1\"] span.tw');"
        "document.body.setAttribute('data-leaf', leaf?('['+leaf.textContent+']'):'MISSING');"
        "var btn=document.querySelector('tr[data-code=\"1\"] button.tw');"
        "document.body.setAttribute('data-btn', btn?('['+btn.textContent+']'):'MISSING');"
    )
    dom = dump_dom(_html(tmp_path), inject=inject)
    assert _attr(dom, "leaf") == "[]"  # 末端の span.tw は空のまま（三角を書かない）
    assert _attr(dom, "btn") == "[▸]"  # 親のボタンは畳んだ印（▸）になる
