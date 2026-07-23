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
    short = render.axis_ticks((date(2026, 8, 3), date(2026, 9, 30)))  # 8/3 は月曜＝格子と揃う
    assert all((later - earlier).days == 7 for earlier, later in zip(short[:-1], short[1:], strict=True))

    year = render.axis_ticks((date(2026, 1, 5), date(2026, 12, 31)))
    assert all(day.day == 1 for day in year[1:])  # 先頭（期間の頭）を除き月ごと（月の頭）
    assert len(year) <= 13

    long_run = render.axis_ticks((date(2026, 1, 5), date(2029, 6, 30)))
    assert len(long_run) <= 17  # 3 年半でも読める数に収まる
    assert all(day.month in {1, 4, 7, 10} for day in long_run[1:])  # 四半期ごと


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


def test_the_gantt_is_the_last_column_right_of_progress(tmp_path: Path) -> None:
    """ガントは表の最後の列（進捗の右）にある。列の並びが崩れたら失敗する。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    header = html.split("<thead>")[1].split("</thead>")[0]
    labels = [re.sub("<[^>]+>", "", cell) for cell in re.findall(r"<th[^>]*>(.*?)</th>", header, re.S)]
    assert labels[-2] == "進捗"  # ガントの 1 つ手前が進捗
    assert 'class="gantt"' in header
    row = _row_markup(html, "T-9001")
    assert row.rindex('class="gantt"') > row.rindex('class="n"')  # 本文でも進捗の右


def test_the_table_stays_narrow_enough_to_show_the_gantt(tmp_path: Path) -> None:
    """左の表を詰めて、ガントが画面外へ押し出されないようにする。

    いちばん見せたい列が最初にスクロールで隠れる、という形にしない。
    """
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    table = re.search(r"table \{[^}]*min-width:(\d+)px", html)
    gantt = re.search(r"th\.gantt, td\.gantt \{[^}]*min-width:(\d+)px", html)
    assert table is not None and gantt is not None
    table_min, gantt_min = int(table.group(1)), int(gantt.group(1))
    assert table_min <= 900
    assert gantt_min >= 260  # ガントに使える幅も確保する


def test_the_first_columns_stay_visible_when_scrolled(tmp_path: Path) -> None:
    """横に溢れても WBS 番号と作業名は左に貼り付く（どの作業の棒かが読める）。印刷では普通の列に戻す。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    assert "th.code, td.code, th.name, td.name { position:sticky;" in html
    printed = html.split("@media print {")[1]
    assert "th.code, td.code, th.name, td.name { position:static; }" in printed


def test_the_axis_shows_the_year_where_it_matters(tmp_path: Path) -> None:
    """軸の日付に年を出す（先頭と、年が変わるところ）。何年の話か分からない工程表を渡さない。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-11-02", "due": "2026-12-25"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2027-01-04", "due": "2027-02-26"},
    )
    html = _render(tmp_path, date(2026, 12, 1))
    labels = re.findall(r'<span class="axis-lab"[^>]*>(.*?)</span>', html)
    assert labels[0].startswith("2026/")  # 先頭は年つき
    assert any(label.startswith("2027/") for label in labels)  # 年が変わったところにも出す
    assert sum(1 for label in labels if "/" in label and label.count("/") == 2) <= 2  # 毎回は出さない


def test_a_finished_row_is_toned_down(tmp_path: Path) -> None:
    """完了した行は落ち着かせる（残っている作業が目に入るように）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "done", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 11))
    assert "is-done" in _row_markup(html, "T-9001")
    assert "is-done" not in _row_markup(html, "T-9002")
    assert "tr.is-done > td { color:var(--muted); }" in html


def test_the_view_has_fold_and_unfold(tmp_path: Path) -> None:
    """全部閉じる／全部展開の操作を出す（階層が深い工程表を 1 手で見渡せるように）。"""
    epic = tmp_path / "work" / "EP-90-alpha"
    _write(epic / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        epic / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    assert 'id="fold"' in html and 'id="unfold"' in html
    assert "全部閉じる" in html and "全部展開" in html


def test_the_header_states_the_period_in_full_dates(tmp_path: Path) -> None:
    """見出しに期間を年月日で出す（軸の目盛だけに頼らせない）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    assert "期間 2026-08-03 〜 2026-08-07" in html


def test_a_short_project_still_gets_dates_on_the_axis() -> None:
    """数日しかない工程でも軸に日付が出る（週や月の格子だけに任せると目盛が 1 つも落ちない）。"""
    one_day = render.axis_ticks((date(2026, 7, 23), date(2026, 7, 23)))
    assert one_day == [date(2026, 7, 23)]

    few_days = render.axis_ticks((date(2026, 7, 23), date(2026, 7, 27)))  # 木曜〜月曜（間に月曜が 1 つ）
    assert few_days[0] == date(2026, 7, 23)
    assert len(few_days) >= 1


def test_the_first_tick_is_always_the_start_of_the_period() -> None:
    """どの粒度でも、期間の頭に目盛がある（軸の左端が何日か分からない、を無くす）。"""
    for span in (
        (date(2026, 8, 3), date(2026, 9, 30)),
        (date(2026, 1, 5), date(2026, 12, 31)),
        (date(2026, 1, 5), date(2029, 6, 30)),
    ):
        assert render.axis_ticks(span)[0] == span[0]
