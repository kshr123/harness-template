"""ガントの図形が実際の日付と合っているかのテスト。

要素が「有る」ことだけを見るテストでは、棒の位置・幅・今日の線がずれても緑のままになる（提出物の
いちばん目立つ部分が黙って間違う）。ここでは**座標を数値で**突き合わせる。

期待値はテストデータの構成から導ける。データの期間 08-03〜08-12 は、描画の窓として週の境目まで広げられる
（月曜 08-03 〜 日曜 08-16 の 14 日）ので、内部座標 1000 に対して 1 日は 1000/14。棒は「開始日の左端」から
「終了日の右端」まで＝終了日を**含む**幅になる。今日の線と節目は、その日の帯の**真ん中**に置く。
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

DATA_SPAN = (date(2026, 8, 3), date(2026, 8, 12))  # 月曜〜水曜（10 日）
WINDOW = render.drawing_window(DATA_SPAN)  # 週の境目まで広げた描画の窓
PER_DAY = 1000.0 / ((WINDOW[1] - WINDOW[0]).days + 1)


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
    assert x == pytest.approx(0.0, abs=0.01)
    assert width == pytest.approx(5 * PER_DAY, abs=0.01)


def test_a_later_bar_is_offset_by_the_elapsed_days(tmp_path: Path) -> None:
    """08-10 は最初の日から 7 日後なので左端 700、幅は 3 日分。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    x, width = _rect(_row_markup(html, "T-9002"), "plan")
    assert x == pytest.approx(7 * PER_DAY, abs=0.01)
    assert width == pytest.approx(3 * PER_DAY, abs=0.01)


def test_a_one_day_bar_is_one_day_wide(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-03"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-12", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 3))  # 遅れの色にならない基準日にする（色でなく幅を見たいので）
    x, width = _rect(_row_markup(html, "T-9001"), "plan")
    assert x == pytest.approx(0.0, abs=0.01)
    assert width == pytest.approx(PER_DAY, abs=0.01)


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
    assert float(match.group(1)) == pytest.approx(2 * PER_DAY + PER_DAY / 2, abs=0.01)  # その日の帯の真ん中


def test_a_milestone_is_centred_on_its_day(tmp_path: Path) -> None:
    """節目の菱形は、その日の帯の**真ん中**に来る（08-12 なら 900 + 50）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9003", "kind": "task", "status": "todo", "due": "2026-08-12", "milestone": True},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    match = re.search(r'<span class="ms" style="left:([\d.]+)%"', _row_markup(html, "T-9003"))
    assert match is not None
    days = (WINDOW[1] - WINDOW[0]).days + 1
    assert float(match.group(1)) == pytest.approx((9 + 0.5) / days * 100, abs=0.01)


def test_a_parent_row_is_drawn_as_a_summary_not_a_bar(tmp_path: Path) -> None:
    """まとめの行（子を持つ行）は、末端と同じ太さの棒で塗らない。

    全部同じ太さの帯が並ぶと階層が図から読めず「ただの帯」に見える。工程表の慣習どおり、
    細い帯と両端の脚で表す。
    """
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
    parent = _row_markup(html, "EP-90")
    leaf = _row_markup(html, "T-9001")
    _, summary_width = _rect(parent, "sum")
    assert summary_width == pytest.approx(10 * PER_DAY, abs=0.01)  # 08-03〜08-12 の全体
    assert not re.search(r'<rect class="(plan|done|late)"', parent)  # 親は棒で塗らない
    assert re.search(r'<rect class="done"', leaf)  # 末端は従来どおりの棒
    _, progress_width = _rect(leaf, "prog")
    assert progress_width == pytest.approx(_rect(leaf, "done")[1], abs=0.01)  # 末端は 1/1 完了


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


def test_each_unit_has_its_own_ticks() -> None:
    """日・週・月・年のそれぞれに目盛の並びがある（単位を切り替えると下段の中身が変わる）。"""
    span = (date(2026, 8, 3), date(2026, 9, 30))
    assert len(render.day_ticks(span)) == (span[1] - span[0]).days + 1
    weeks = render.week_ticks(span)
    assert all((later - earlier).days == 7 for earlier, later in zip(weeks[:-1], weeks[1:], strict=True))
    assert [d.day for d in render.month_ticks(span)[1:]] == [1]  # 9/1 だけ
    assert render.year_ticks((date(2026, 5, 1), date(2027, 5, 1)))[1:] == [date(2027, 1, 1)]


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
    assert "axis-lab" in axis


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
    labels = re.findall(r'<span class="axis-lab lab-(\w+)"[^>]*>(.*?)</span>', html)
    plain = [text for kind, text in labels if kind == "m"]  # 下段に出す月（年を付けない）
    with_year = [text for kind, text in labels if kind == "my"]  # 上段に出す月（年を添える）
    years = [text for kind, text in labels if kind == "y"]
    assert with_year[0].startswith("2026年")  # 先頭は年つき
    assert any(text.startswith("2027年") for text in with_year)  # 年が変わったところにも出す
    assert sum(1 for text in with_year if "年" in text) <= 2  # 毎回は出さない
    assert all("年" not in text for text in plain)  # 上下で年が二重に出ない
    assert years == ["2026年", "2027年"]


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
    assert "すべて折りたたむ" in html and "すべて展開" in html


def test_the_header_states_the_period_in_full_dates(tmp_path: Path) -> None:
    """見出しに期間を年月日で出す（軸の目盛だけに頼らせない）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    assert "期間 2026-08-03 〜 2026-08-07" in html


def test_the_first_tick_is_always_the_start_of_the_period() -> None:
    """どの粒度でも、期間の頭に目盛がある（軸の左端が何日か分からない、を無くす）。"""
    for span in (
        (date(2026, 8, 3), date(2026, 9, 30)),
        (date(2026, 1, 5), date(2026, 12, 31)),
        (date(2026, 1, 5), date(2029, 6, 30)),
    ):
        for ticks in (render.week_ticks(span), render.month_ticks(span), render.year_ticks(span)):
            assert ticks[0] == span[0]


def test_the_drawing_window_snaps_to_weeks_and_has_a_floor() -> None:
    """描画の窓は週の境目に揃え、最低 2 週間を確保する。

    データの期間をそのまま使うと、数日の案件で棒が列の端から端まで伸びて「ただの帯」になる。
    """
    one_day = render.drawing_window((date(2026, 7, 23), date(2026, 7, 23)))  # 木曜 1 日だけ
    assert one_day[0].weekday() == 0 and one_day[1].weekday() == 6  # 月曜〜日曜
    assert (one_day[1] - one_day[0]).days + 1 >= 14
    assert one_day[0] <= date(2026, 7, 23) <= one_day[1]

    long_run = render.drawing_window((date(2026, 8, 3), date(2026, 12, 18)))
    assert long_run[0] == date(2026, 8, 3)  # 既に月曜なので動かない
    assert long_run[1].weekday() == 6


def test_a_one_day_project_does_not_fill_the_whole_column(tmp_path: Path) -> None:
    """期間が 1 日の木でも、棒は列いっぱいにならない（緑の帯にしか見えない状態を無くす）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "done", "start": "2026-07-23", "due": "2026-07-23"},
    )
    html = _render(tmp_path, date(2026, 7, 23))
    _, width = _rect(_row_markup(html, "T-9001"), "done")
    assert width < 1000.0 / 10  # 窓は最低 14 日あるので、1 日の棒は全体の 1/14 以下


def test_every_row_carries_the_time_grid(tmp_path: Path) -> None:
    """各行に時間軸の格子が引かれる（棒だけだと図表に見えない）。位置は軸の目盛と一致する。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    row = _row_markup(html, "T-9001")
    grid = [float(x) for x in re.findall(r'<line class="grid g-w" x1="([\d.]+)"', row)]
    ticks = [render._x_of(day, WINDOW) for day in render.week_ticks(WINDOW)[1:]]
    assert grid == pytest.approx(ticks, abs=0.01)
    assert grid, "格子が 1 本も引かれていない"


def test_non_working_days_are_shaded(tmp_path: Path) -> None:
    """土日・祝日・案件の休業日に帯が敷かれる（営業日で数えていることが図でも分かる）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    row = _row_markup(html, "T-9001")
    bands = [(float(x), float(w)) for x, w in re.findall(r'<rect class="off" x="([\d.]+)"[^>]*width="([\d.]+)"', row)]
    # 窓は 08-03（月）〜08-16（日）。土日は 08-08〜08-09 と 08-15〜08-16 の 2 か所。
    assert len(bands) == 2
    assert bands[0][0] == pytest.approx(5 * PER_DAY, abs=0.01)  # 最初の土曜＝5 日後
    assert bands[0][1] == pytest.approx(2 * PER_DAY, abs=0.01)  # 土日の 2 日分


def test_both_the_week_and_month_grids_are_available(tmp_path: Path) -> None:
    """週と月の両方の目盛を書き出しておく（単位の切り替えでサーバへ行かないため）。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-12-18"},
    )
    html = _render(tmp_path, date(2026, 9, 1))
    row = _row_markup(html, "T-9001")
    assert re.search(r'<line class="grid g-w"', row)
    assert re.search(r'<line class="grid g-m"', row)
    assert 'class="axis-lab lab-w"' in html
    assert 'class="axis-lab lab-m"' in html


def test_the_view_offers_the_gantt_units(tmp_path: Path) -> None:
    """ガントの単位（自動・月・週・日）を選ぶ操作が画面にある。"""
    _tree(
        tmp_path,
        {"id": "T-9001", "kind": "task", "status": "todo", "start": "2026-08-03", "due": "2026-08-07"},
    )
    html = _render(tmp_path, date(2026, 8, 5))
    for unit in ("m", "w", "d"):
        assert f'data-zoom="{unit}"' in html
    assert 'data-zoom="auto"' not in html  # 「自動」は状態ではなく初期値の決め方なので選択肢に出さない
    assert "data-days=" in html and "data-unit=" in html  # 幅の計算と初期の単位を画面が持っている
