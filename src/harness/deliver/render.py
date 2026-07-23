"""WBS を自己完結の HTML 1 ファイルに描く（行レンダラ＋外殻）。

外部リソースを一切読まない（CSS もスクリプトも本文に埋め込む・画像もフォントも外から取らない）＝
クライアントの担当者がファイル 1 つを社内へ転送しても、そのまま開ける。

**構造の要**：左に表・右に大きな 1 枚のガント、という 2 枚組にはしない。1 つの表にして、ガントのバーは
各行のセルの中に小さな SVG として描く。こうすると改ページで行とバーがずれず、時間軸の見出しを各ページに
再掲でき（`display: table-header-group`）、行単位で改ページを避けられる（`break-inside: avoid`）。
提出物として印刷に耐える形はこれだけ。今日の線も各行の SVG に同じ位置で描く＝行ごとに完結するのでずれない。

横軸は暦日の一次変換にする（営業日で詰めると、休みを挟む工程の長さが見た目と合わなくなる）。営業日は
「日数」列の数字で示す＝軸の直感と数え方の正しさを両立させる。
"""

from __future__ import annotations

import html
from datetime import date, timedelta

from harness.deliver.wbs import Wbs, WbsRow
from harness.models import Status

# 状態の表示名（顧客に見せる語）。コード側の語彙（Status）を 2 つに増やさないための表示専用の対応表。
_STATUS_LABEL: dict[Status, str] = {
    Status.todo: "未着手",
    Status.in_progress: "進行中",
    Status.in_review: "確認中",
    Status.blocked: "停止",
    Status.done: "完了",
}

_COLUMNS = ("WBS", "作業", "チーム", "担当", "状態", "予定開始", "予定終了", "日数", "実績開始", "実績終了", "進捗")

# ガントの SVG の内部座標の幅（viewBox の幅）。実際の表示幅は CSS が決める（preserveAspectRatio="none"）。
_CANVAS = 1000.0


def _esc(value: object) -> str:
    """HTML に埋める文字列（None は空文字）。"""
    return "" if value is None else html.escape(str(value))


def _day_label(value: date | None) -> str:
    return "" if value is None else value.strftime("%m/%d")


def _x_of(day: date, span: tuple[date, date]) -> float:
    """暦日を SVG の内部座標へ移す（期間の最初の日が 0・最後の日の翌日が _CANVAS）。"""
    first, last = span
    total = (last - first).days + 1
    return (day - first).days * (_CANVAS / total)


def _bar_svg(row: WbsRow, span: tuple[date, date], today: date) -> str:
    """1 行分のガント（その行のセルに収まる小さな SVG）。バー・節目・進捗・今日の線をこの中で完結させる。"""
    first, last = span
    scale = _CANVAS / ((last - first).days + 1)
    parts: list[str] = [f'<svg class="bar" viewBox="0 0 {_CANVAS:.0f} 14" preserveAspectRatio="none" role="img">']
    if first <= today <= last:
        tx = _x_of(today, span)
        parts.append(f'<line class="today" x1="{tx:.2f}" y1="0" x2="{tx:.2f}" y2="14" />')
    if row.milestone and row.due is not None:
        cx = _x_of(row.due, span) + scale / 2
        parts.append(f'<polygon class="ms" points="{cx - 6:.2f},7 {cx:.2f},1 {cx + 6:.2f},7 {cx:.2f},13" />')
    elif row.start is not None and row.due is not None:
        x = _x_of(row.start, span)
        width = max(_x_of(row.due, span) + scale - x, 2.0)
        kind = "late" if row.late else ("done" if row.status is Status.done else "plan")
        parts.append(f'<rect class="{kind}" x="{x:.2f}" y="3" width="{width:.2f}" height="8" rx="2" />')
        if row.done_leaves:
            parts.append(f'<rect class="prog" x="{x:.2f}" y="5" width="{width * row.progress:.2f}" height="4" />')
    parts.append("</svg>")
    return "".join(parts)


def _axis_svg(span: tuple[date, date], today: date) -> str:
    """時間軸の見出し（週の頭に目盛）。表の見出し行に入るので、印刷時は各ページに再掲される。"""
    first, last = span
    ticks: list[str] = []
    day = first - timedelta(days=first.weekday())  # 直前の月曜から週ごとに
    while day <= last:
        if day >= first:
            x = _x_of(day, span)
            ticks.append(f'<line x1="{x:.2f}" y1="7" x2="{x:.2f}" y2="14" />')
            ticks.append(f'<text x="{x + 3:.2f}" y="6">{day.strftime("%-m/%-d")}</text>')
        day += timedelta(days=7)
    if first <= today <= last:
        tx = _x_of(today, span)
        ticks.append(f'<line class="today" x1="{tx:.2f}" y1="0" x2="{tx:.2f}" y2="14" />')
    head = f'<svg class="axis" viewBox="0 0 {_CANVAS:.0f} 14" preserveAspectRatio="none" role="img">'
    return head + "".join(ticks) + "</svg>"


def _row_html(row: WbsRow, span: tuple[date, date] | None, today: date) -> str:
    """WBS の 1 行。節・作業単位・手動行を同じ描き方で出す（行の描き方は 1 つだけ）。"""
    depth = row.code.count(".")
    classes = [f"lv{depth}", f"src-{row.source}"]
    if row.late:
        classes.append("is-late")
    unscheduled = not row.children and not row.scheduled
    if unscheduled:
        classes.append("is-unscheduled")
    name = _esc(row.name)
    if unscheduled:
        name += '<span class="tag">未日程</span>'
    if row.ref:
        name += f'<span class="ref">{_esc(row.ref)}</span>'
    cells = [
        f'<td class="code">{_esc(row.code)}</td>',
        f'<td class="name">{name}</td>',
        f"<td>{_esc(row.team)}</td>",
        f"<td>{_esc('、'.join(row.assignees))}</td>",
        f"<td>{_esc(_STATUS_LABEL[row.status]) if row.status is not None else ''}</td>",
        f'<td class="d">{_day_label(row.start)}</td>',
        f'<td class="d">{_day_label(row.due)}</td>',
        f'<td class="n">{"" if row.workdays is None else row.workdays}</td>',
        f'<td class="d">{_day_label(row.actual_start)}</td>',
        f'<td class="d">{_day_label(row.actual_finish)}</td>',
        f'<td class="n">{f"{row.done_leaves}/{row.total_leaves}" if row.total_leaves else ""}</td>',
        f'<td class="gantt">{_bar_svg(row, span, today) if span else ""}</td>',
    ]
    return f'<tr class="{" ".join(classes)}">{"".join(cells)}</tr>'


# 配色は「紙に刷った工程表」を基準に、画面で見るとき用に暗い地の版も持つ（印刷は常に紙の版に固定）。
# 灰は中立の灰でなく、棒の青へわずかに寄せた寒色寄りにして、地と棒が同じ絵に見えるようにする。
# 和文の書体はファイルに埋め込めない（数 MB になる）ので、日本語の業務文書で確実に出る系統だけを並べる。
_STYLE = """
:root {
  --paper:#fbfbfa; --ink:#1b1f24; --muted:#6b7280; --line:#d8dbe0; --sec:#eef2f7;
  --plan:#5b87b8; --done:#4f9d72; --late:#c8635a; --prog:#2f6f4f; --today:#c8635a;
  --tag-bg:#fdf1d6; --tag-ink:#8a6116; --late-ink:#a8352a;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper:#16181c; --ink:#e6e8ea; --muted:#98a1ad; --line:#333941; --sec:#1f242b;
    --plan:#6f9fd0; --done:#5fb587; --late:#dd7d72; --prog:#8ed7ae; --today:#dd7d72;
    --tag-bg:#3a3020; --tag-ink:#e3c07a; --late-ink:#f0958b;
  }
}
:root[data-theme="dark"] {
  --paper:#16181c; --ink:#e6e8ea; --muted:#98a1ad; --line:#333941; --sec:#1f242b;
  --plan:#6f9fd0; --done:#5fb587; --late:#dd7d72; --prog:#8ed7ae; --today:#dd7d72;
  --tag-bg:#3a3020; --tag-ink:#e3c07a; --late-ink:#f0958b;
}
:root[data-theme="light"] {
  --paper:#fbfbfa; --ink:#1b1f24; --muted:#6b7280; --line:#d8dbe0; --sec:#eef2f7;
  --plan:#5b87b8; --done:#4f9d72; --late:#c8635a; --prog:#2f6f4f; --today:#c8635a;
  --tag-bg:#fdf1d6; --tag-ink:#8a6116; --late-ink:#a8352a;
}
* { box-sizing:border-box; }
body { margin:0; padding:16px 20px; color:var(--ink); background:var(--paper);
       font:13px/1.5 "Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif; }
header { border-bottom:2px solid var(--ink); padding-bottom:8px; margin-bottom:12px; }
h1 { font-size:17px; margin:0 0 2px; }
.meta { color:var(--muted); font-size:11px; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; min-width:1100px; }
thead { display:table-header-group; }
th, td { border:1px solid var(--line); padding:2px 5px; vertical-align:middle; white-space:nowrap; }
th { background:var(--sec); font-weight:600; font-size:11px; text-align:left; }
tr { break-inside:avoid; }
td.code { color:var(--muted); font-variant-numeric:tabular-nums; }
td.d, td.n { text-align:right; font-variant-numeric:tabular-nums; font-size:12px; }
td.name { white-space:normal; min-width:220px; }
td.gantt { width:45%; min-width:340px; padding:0 2px; }
.ref { color:var(--muted); font-size:10px; margin-left:6px; }
.tag { background:var(--tag-bg); color:var(--tag-ink); font-size:10px; padding:0 4px; margin-left:6px;
       border-radius:2px; }
tr.lv0 > td { background:var(--sec); font-weight:600; }
tr.lv1 td.name { padding-left:18px; }
tr.lv2 td.name { padding-left:34px; }
tr.lv3 td.name { padding-left:50px; }
tr.is-late td.d, tr.is-late td.name { color:var(--late-ink); }
svg.bar, svg.axis { display:block; width:100%; height:14px; }
svg.axis text { font-size:7px; fill:var(--muted); }
svg.axis line { stroke:var(--line); stroke-width:1; }
rect.plan { fill:var(--plan); } rect.done { fill:var(--done); } rect.late { fill:var(--late); }
rect.prog { fill:var(--prog); opacity:.75; } polygon.ms { fill:var(--ink); }
line.today { stroke:var(--today); stroke-width:1.2; stroke-dasharray:2 2; }
footer { margin-top:14px; font-size:11px; color:var(--muted); }
footer h2 { font-size:12px; color:var(--ink); margin:10px 0 4px; }
.legend span { margin-right:14px; }
.legend i { display:inline-block; width:16px; height:8px; border-radius:2px; vertical-align:middle; margin-right:4px; }
@media print {
  /* 印刷は常に紙の版に固定する（暗い地のまま刷ると読めない・インクも無駄になる）。 */
  :root {
    --paper:#fff; --ink:#1b1f24; --muted:#6b7280; --line:#d8dbe0; --sec:#eef2f7;
    --plan:#5b87b8; --done:#4f9d72; --late:#c8635a; --prog:#2f6f4f; --today:#c8635a;
    --tag-bg:#fdf1d6; --tag-ink:#8a6116; --late-ink:#a8352a;
  }
  @page { size:A3 landscape; margin:8mm; }
  body { padding:0; font-size:10px; }
  .scroll { overflow:visible; }
  table { min-width:0; }
  td.gantt { min-width:0; }
}
"""


def _legend() -> str:
    return (
        '<p class="legend">'
        '<span><i style="background:var(--plan)"></i>予定</span>'
        '<span><i style="background:var(--done)"></i>完了</span>'
        '<span><i style="background:var(--late)"></i>遅れ（予定終了を過ぎて未完）</span>'
        '<span><i style="background:var(--ink);width:8px;height:8px;transform:rotate(45deg)"></i>節目</span>'
        "<span>破線＝基準日</span></p>"
    )


def render_html(wbs: Wbs, *, provenance: str = "", draft: bool = False) -> str:
    """WBS 一式を自己完結 HTML（本文）に描く。

    `provenance` は生成物の由来（どのコミット・いつ・どの木から出たか）を 1 行で表した文字列。
    `draft` を立てると下書きと分かる表示にする（未コミットの変更を含む生成物を、そうと分かる形でだけ許す）。
    """
    span = wbs.span
    head = "".join(f"<th>{_esc(c)}</th>" for c in _COLUMNS)
    axis = f'<th class="gantt">{_axis_svg(span, wbs.today) if span else ""}</th>'
    body = "".join(_row_html(row, span, wbs.today) for row in wbs.walk())
    title = wbs.overlay.project or "WBS"
    client = f"<div>提出先: {_esc(wbs.overlay.client)}</div>" if wbs.overlay.client else ""
    unscheduled = wbs.unscheduled
    notes = ""
    if unscheduled:
        ids = "、".join(_esc(r.ref or r.name) for r in unscheduled)
        notes = f"<h2>未日程（{len(unscheduled)} 件）</h2><p>予定を置いていない作業: {ids}</p>"
    banner = '<div class="meta" style="color:#a8352a">下書き（未コミットの変更を含む）</div>' if draft else ""
    return (
        f"<style>{_STYLE}</style>"
        f"<header><h1>{_esc(title)}</h1>{client}"
        f'<div class="meta">基準日 {wbs.today.isoformat()}　{_esc(provenance)}</div>{banner}</header>'
        f'<div class="scroll"><table><thead><tr>{head}{axis}</tr></thead><tbody>{body}</tbody></table></div>'
        f"<footer>{_legend()}{notes}</footer>"
    )
