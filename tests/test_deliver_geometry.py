"""ガントの図形が実際の日付と合っているかのテスト。

要素が「有る」ことだけを見るテストでは、棒の位置・幅・今日の線がずれても緑のままになる（提出物の
いちばん目立つ部分が黙って間違う）。ここでは**座標を数値で**突き合わせる。

期待値はテストデータの構成から導ける：期間 08-03〜08-12 は 10 日なので、内部座標 1000 に対して 1 日 100。
棒は「開始日の左端」から「終了日の右端」まで＝終了日を**含む**幅になる。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from harness.deliver import render
from harness.deliver import wbs as wbs_mod
from harness.deliver.overlay import Overlay

pytestmark = pytest.mark.unit

FIRST = date(2026, 8, 3)  # 期間の最初の日（月曜）
LAST = date(2026, 8, 12)  # 期間の最後の日（水曜）＝10 日間
PER_DAY = 1000.0 / 10  # 内部座標 1000 を 10 日で割る


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _tree(root: Path, *items: dict[str, Any]) -> None:
    for item in items:
        _write(root / "work" / f"{item['id']}-x.md", item)


def _row_markup(html: str, item_id: str) -> str:
    """その単位の行だけを取り出す。"""
    return next(part for part in html.split("<tr") if item_id in part)


def _rect(markup: str, kind: str) -> tuple[float, float]:
    """行の中の矩形の x と幅。"""
    match = re.search(rf'<rect class="{kind}" x="([\d.]+)" y="\d+" width="([\d.]+)"', markup)
    assert match is not None, f"{kind} の矩形が無い: {markup[:400]}"
    return float(match.group(1)), float(match.group(2))


def _render(root: Path, today: date) -> str:
    return render.render_html(wbs_mod.build(root, today=today, overlay=Overlay()))


def test_a_bar_starts_at_its_start_day_and_covers_its_end_day(tmp_path: Path) -> None:
    """08-03〜08-07 の棒は、左端 0・幅 5 日分（終了日を含む）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    x, width = _rect(_row_markup(html, "T-9001"), "plan")
    assert x == pytest.approx(0.0)
    assert width == pytest.approx(5 * PER_DAY)


def test_a_later_bar_is_offset_by_the_elapsed_days(tmp_path: Path) -> None:
    """08-10 は最初の日から 7 日後なので左端 700、幅は 3 日分。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    x, width = _rect(_row_markup(html, "T-9002"), "plan")
    assert x == pytest.approx(7 * PER_DAY)
    assert width == pytest.approx(3 * PER_DAY)


def test_a_one_day_bar_is_one_day_wide(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-03"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-12", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 3))  # 遅れの色にならない基準日にする（色でなく幅を見たいので）
    x, width = _rect(_row_markup(html, "T-9001"), "plan")
    assert x == pytest.approx(0.0)
    assert width == pytest.approx(PER_DAY)


def test_the_today_line_sits_on_the_day_it_names(tmp_path: Path) -> None:
    """08-05 は最初の日から 2 日後なので、線は 200 の位置に来る。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    match = re.search(r'<line class="today" x1="([\d.]+)"', _row_markup(html, "T-9001"))
    assert match is not None
    assert float(match.group(1)) == pytest.approx(2 * PER_DAY)


def test_a_milestone_is_centred_on_its_day(tmp_path: Path) -> None:
    """節目の菱形は、その日の帯の**真ん中**に来る（08-12 なら 900 + 50）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9003", "kind": "task", "status": "todo", "due": "2026-08-12", "milestone": True},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    match = re.search(r'<polygon class="ms" points="[\d.]+,7 ([\d.]+),1', _row_markup(html, "T-9003"))
    assert match is not None
    assert float(match.group(1)) == pytest.approx(9 * PER_DAY + PER_DAY / 2)


def test_the_progress_overlay_is_as_wide_as_the_share_done(tmp_path: Path) -> None:
    """子 2 件のうち 1 件 done の親は、棒の半分だけ進捗の帯が乗る。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        epic / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "done", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        epic / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    markup = _row_markup(html, "EP-90")
    _, bar_width = _rect(markup, "plan")
    _, progress_width = _rect(markup, "prog")
    assert bar_width == pytest.approx(10 * PER_DAY)  # 08-03〜08-12 の全体
    assert progress_width == pytest.approx(bar_width / 2)  # 末端 2 件のうち 1 件 done


def test_a_task_due_exactly_today_is_not_late_yet(tmp_path: Path) -> None:
    """予定終了が今日の作業は、まだ遅れではない（今日いっぱいある）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 7))
    assert "is-late" not in _row_markup(html, "T-9001")
    html_next_day = _render(tmp_path, date(2026, 8, 8))
    assert "is-late" in _row_markup(html_next_day, "T-9001")


def test_the_axis_thins_out_for_long_projects() -> None:
    """短い案件は週ごと、長い案件は月・四半期ごとに間引く（目盛が重なって読めなくなるのを防ぐ）。"""
    short = render.axis_ticks((date(2026, 8, 3), date(2026, 9, 30)))
    assert all((later - earlier).days == 7 for earlier, later in zip(short[:-1], short[1:], strict=True))

    year = render.axis_ticks((date(2026, 1, 5), date(2026, 12, 31)))
    assert all(day.day == 1 for day in year)  # 月ごと（月の頭）
    assert len(year) <= 12

    long_run = render.axis_ticks((date(2026, 1, 5), date(2029, 6, 30)))
    assert len(long_run) <= 16  # 3 年半でも読める数に収まる
    assert all(day.month in {1, 4, 7, 10} for day in long_run)  # 四半期ごと


def test_the_output_is_a_complete_document(tmp_path: Path) -> None:
    """断片でなく完全な文書として出す（文字コードの宣言が無いと受け手の環境で日本語が化ける）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    assert html.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in html
    assert '<html lang="ja">' in html
    assert "<title>" in html
    assert html.rstrip().endswith("</html>")


def test_the_axis_labels_are_not_stretched_with_the_bars(tmp_path: Path) -> None:
    """日付の文字は引き伸ばす図形の中に置かない（列の幅次第で潰れる／伸びるため）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    axis = html.split('<div class="axis-wrap">')[1].split("</div>")[0]
    assert "<text" not in axis  # 文字は SVG の外
    assert 'class="axis-lab"' in axis
