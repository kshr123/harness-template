"""WBS の不変条件の検査のテスト。

「黙って行が消える／二重に数える」経路を、どれも既定で不合格にできているかを確かめる。
どの検査も、指摘の有無を**そこだけを壊した木**との差で見る（合格する形をまず作ってから 1 か所ずつ壊す）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from harness.deliver import wbs_lint
from harness.deliver.overlay import Overlay

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 20)


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """EP-90（子 2 件）と EP-91（末端）。日程は矛盾の無い状態に置く。"""
    alpha = root / "work" / "EP-90-alpha"
    _write(alpha / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        alpha / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "done", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        alpha / "T-9002-b.md",
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
        root / "work" / "EP-91-beta" / "item.md",
        {"id": "EP-91", "kind": "epic", "status": "todo", "start": "2026-08-17", "due": "2026-08-21"},
    )


def _errors(root: Path, overlay: Overlay | None = None) -> list[str]:
    problems = wbs_lint.check(root, today=TODAY, overlay=overlay if overlay is not None else Overlay())
    return [p.message for p in problems if p.level == "error"]


def _covering_overlay(**extra: Any) -> Overlay:
    """EP-90 と EP-91 を漏れなく覆う、合格する節構成（ここから 1 か所ずつ壊す）。"""
    payload: dict[str, Any] = {
        "sections": [
            {"name": "設計", "entries": [{"work": "EP-90"}]},
            {"name": "構築", "entries": [{"work": "EP-91"}]},
        ]
    }
    payload.update(extra)
    return Overlay.model_validate(payload)


def test_a_covering_overlay_passes(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    assert _errors(tmp_path, _covering_overlay()) == []


def test_no_overlay_requires_nothing(tmp_path: Path) -> None:
    """上書きを書かない案件では、覆いの検査は何も要求しない（木をそのまま出すので漏れが起きない）。"""
    _scaffold(tmp_path)
    assert _errors(tmp_path) == []


def test_uncovered_work_unit_fails(tmp_path: Path) -> None:
    """節構成が覆っていない単位があれば失敗する（顧客向けから黙って消えるのを止める）。"""
    _scaffold(tmp_path)
    overlay = Overlay.model_validate({"sections": [{"name": "設計", "entries": [{"work": "EP-90"}]}]})
    messages = _errors(tmp_path, overlay)
    assert len(messages) == 1
    assert "EP-91" in messages[0]


def test_excluded_work_unit_is_allowed(tmp_path: Path) -> None:
    """外すと決めた単位は exclude に書けば通る（外したことが差分に残る）。"""
    _scaffold(tmp_path)
    overlay = Overlay.model_validate(
        {"sections": [{"name": "設計", "entries": [{"work": "EP-90"}]}], "exclude": ["EP-91"]}
    )
    assert _errors(tmp_path, overlay) == []


def test_same_work_unit_in_two_sections_fails(tmp_path: Path) -> None:
    """同じ単位を 2 つの節が指すと進捗が二重に数えられるので失敗する。"""
    _scaffold(tmp_path)
    overlay = Overlay.model_validate(
        {
            "sections": [
                {"name": "設計", "entries": [{"work": "EP-90"}]},
                {"name": "再掲", "entries": [{"work": "EP-90"}]},
                {"name": "構築", "entries": [{"work": "EP-91"}]},
            ]
        }
    )
    messages = _errors(tmp_path, overlay)
    assert len(messages) == 1
    assert "2 つ以上の節" in messages[0]


def test_manual_row_that_no_section_shows_fails(tmp_path: Path) -> None:
    """定義したのにどの節も参照していない手動行は失敗（書いたのに出ない行を作らない）。"""
    _scaffold(tmp_path)
    overlay = _covering_overlay(rows=[{"id": "W-001", "name": "承認", "status": "todo"}])
    messages = _errors(tmp_path, overlay)
    assert len(messages) == 1
    assert "W-001" in messages[0]


def test_section_pointing_at_a_missing_manual_row_fails(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    overlay = Overlay.model_validate(
        {
            "sections": [
                {"name": "設計", "entries": [{"work": "EP-90"}, {"row": "W-404"}]},
                {"name": "構築", "entries": [{"work": "EP-91"}]},
            ]
        }
    )
    messages = _errors(tmp_path, overlay)
    assert len(messages) == 1
    assert "W-404" in messages[0]


def test_parent_declaring_its_own_dates_fails(tmp_path: Path) -> None:
    """子を持つ単位が自分で日程を宣言していたら失敗する（親の日程は子から導くので必ず食い違う）。"""
    _scaffold(tmp_path)
    _write(
        tmp_path / "work" / "EP-90-alpha" / "item.md",
        {
            "id": "EP-90",
            "kind": "epic",
            "status": "in-progress",
            "plan": "detailed",
            "start": "2026-08-01",
            "due": "2026-08-31",
        },
    )
    messages = _errors(tmp_path)
    assert len(messages) == 1
    assert "EP-90" in messages[0]


def test_leaf_declaring_its_own_dates_is_fine(tmp_path: Path) -> None:
    """子のいない単位（未分解のエピック）が日程を持つのは正常＝提案時の粗い粒度で描ける。"""
    _scaffold(tmp_path)
    assert _errors(tmp_path) == []


def test_successor_starting_before_its_predecessor_ends_fails(tmp_path: Path) -> None:
    """先行する単位の終了予定より後続の開始予定が前なら失敗（依存と日程の矛盾）。"""
    _scaffold(tmp_path)
    _write(
        tmp_path / "work" / "EP-90-alpha" / "T-9002-b.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "todo",
            "start": "2026-08-05",  # 先行 T-9001 の終了予定（08-07）より前
            "due": "2026-08-12",
            "depends_on": ["T-9001"],
        },
    )
    messages = _errors(tmp_path)
    assert len(messages) == 1
    assert "T-9002" in messages[0]
