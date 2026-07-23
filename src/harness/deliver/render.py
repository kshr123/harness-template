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
STATUS_LABEL: dict[Status, str] = {
    Status.todo: "未着手",
    Status.in_progress: "進行中",
    Status.in_review: "確認中",
    Status.blocked: "停止",
    Status.done: "完了",
}

# 表の列（見出しと、幅・寄せを決める区分）。見出しの並びは形式に依らないので、表計算もここから引く。
COLUMNS: tuple[tuple[str, str], ...] = (
    ("WBS", "code"),
    ("作業", "name"),
    ("チーム", "who"),
    ("担当", "who"),
    ("状態", "st"),
    ("予定開始", "d"),
    ("予定終了", "d"),
    ("日数", "n"),
    ("実績開始", "d"),
    ("実績終了", "d"),
    ("進捗", "n"),
)

COLUMN_LABELS: tuple[str, ...] = tuple(label for label, _ in COLUMNS)

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


def axis_ticks(span: tuple[date, date]) -> list[date]:
    """時間軸に打つ目盛の日付。**期間の長さで間引く**（案件が長いほど粗くする）。

    週ごとに固定すると、2 年を超える案件で 100 個以上の日付が重なって読めなくなる（実際に起きる）。
    軸は「いつ頃か」が読めればよいので、目安として 30 個程度に収まる粒度へ落とす。
    """
    first, last = span
    days = (last - first).days + 1
    out: list[date] = []
    if days <= 120:  # 4 か月まで＝週ごと（月曜）
        day = first - timedelta(days=first.weekday())
        while day <= last:
            if day >= first:
                out.append(day)
            day += timedelta(days=7)
    else:
        step = 1 if days <= 900 else 3  # 2 年半までは月ごと、それを超えたら四半期ごと
        year, month = first.year, first.month
        while True:
            current = date(year, month, 1)
            if current > last:
                break
            if current >= first:
                out.append(current)
            month += step
            while month > 12:
                year, month = year + 1, month - 12
    # 期間の頭には必ず目盛を打つ。週や月の格子だけに任せると、**短い期間で目盛が 1 つも落ちない**
    # （数日の工程は、格子の線がその期間の外にしか無い）＝軸から日付が消える。
    if not out or out[0] != first:
        crowded = bool(out) and (out[0] - first).days * (_CANVAS / days) < 40  # 近すぎる目盛は片方だけ残す
        out = [first, *out[1:]] if crowded else [first, *out]
    return out


def _axis_svg(span: tuple[date, date], today: date) -> str:
    """時間軸の見出し。表の見出し行に入るので、印刷時は各ページに再掲される。

    目盛の線は棒と同じ引き伸ばし（`preserveAspectRatio="none"`）で位置を合わせるが、**日付の文字は
    SVG に入れない**。引き伸ばすと文字まで横に潰れる／伸びるため、文字は HTML の要素として割合の位置に
    重ねる（列の実幅がいくつでも読める）。
    """
    first, last = span
    ticks: list[str] = []
    labels: list[str] = []
    total = (last - first).days + 1
    monthly = total > 120  # 目盛の粒度は期間の長さで決まる（axis_ticks と同じ境目）
    shown_year: int | None = None
    for day in axis_ticks(span):
        x = _x_of(day, span)
        ticks.append(f'<line x1="{x:.2f}" y1="7" x2="{x:.2f}" y2="14" />')
        # 書式指定子の `%-m` は Windows で例外になるので、数を直に組む（他プロファイルと同じく Windows も想定）。
        # 年は、先頭と年が変わるところに出す（毎回出すと重なって読めない・出さないと何年の話か分からない）。
        stem = f"{day.month}" if monthly else f"{day.month}/{day.day}"
        text = f"{day.year}/{stem}" if day.year != shown_year else stem
        shown_year = day.year
        labels.append(f'<span class="axis-lab" style="left:{(day - first).days / total * 100:.3f}%">{text}</span>')
    if first <= today <= last:
        tx = _x_of(today, span)
        ticks.append(f'<line class="today" x1="{tx:.2f}" y1="0" x2="{tx:.2f}" y2="14" />')
    head = f'<svg class="axis" viewBox="0 0 {_CANVAS:.0f} 14" preserveAspectRatio="none" role="img">'
    return f'<div class="axis-wrap">{head}{"".join(ticks)}</svg>{"".join(labels)}</div>'


def _editable_fields(row: WbsRow) -> dict[str, str]:
    """その行で直せる欄（表示上の列 → 正本のキー）。導出値・節の行はここに出てこない。

    表題は親でも直せる（保存された値だから）。日程・状態・担当は末端だけ＝親の値は子から導くので、
    直す先が無い（画面に編集の口を作らないことで、そもそも矛盾を入力できない）。
    """
    if row.path is None:
        return {}
    manual = row.source == "manual"
    fields = {"name": "name" if manual else "title"}
    if row.children:
        return fields
    fields["status"] = "status"
    fields["start"] = "start"
    fields["due"] = "due"
    if manual:
        fields["team"] = "team"
    else:
        fields["assignees"] = "owner"
    return fields


def _cell(column: str, inner: str, raw: str, row: WbsRow, fields: dict[str, str], digest: str, *, css: str = "") -> str:
    """1 つのセル。直せる欄なら、書き戻し先（ID・キー・読んだ時点の指紋）を持たせる。"""
    field = fields.get(column)
    klass = f' class="{css}"' if css else ""
    if field is None or row.ref is None:
        return f"<td{klass}>{inner}</td>"
    attrs = (
        f' class="edit{" " + css if css else ""}" data-ref="{_esc(row.ref)}" data-field="{_esc(field)}"'
        f' data-value="{_esc(raw)}" data-base="{_esc(digest)}"'
    )
    return f'<td{attrs} tabindex="0">{inner or '<span class="blank">＋</span>'}</td>'


def _row_html(row: WbsRow, span: tuple[date, date] | None, today: date, *, editable: bool = False) -> str:
    """WBS の 1 行。節・作業単位・手動行を同じ描き方で出す（行の描き方は 1 つだけ）。

    編集できる状態でも描き方は変えない（直せる欄に書き戻し先の目印が増えるだけ）＝閲覧用と編集用で
    2 つの描き方を持たない。
    """
    depth = row.code.count(".")
    classes = [f"lv{depth}", f"src-{row.source}"]
    if row.late:
        classes.append("is-late")
    if row.status is Status.done:
        classes.append("is-done")
    unscheduled = not row.children and not row.scheduled
    if unscheduled:
        classes.append("is-unscheduled")
    name = _esc(row.name)
    if unscheduled:
        name += '<span class="tag">未日程</span>'
    if row.ref:
        name += f'<span class="ref">{_esc(row.ref)}</span>'
    fields = _editable_fields(row) if editable else {}
    digest = _digest_of(row) if fields else ""
    status_label = STATUS_LABEL[row.status] if row.status is not None else ""
    # 折りたたみの取っ手は WBS 番号の列に置く（表題の列は直せる欄なので、押すたびに編集が始まってしまう）。
    toggle = f'<button class="tw" type="button" data-code="{_esc(row.code)}" aria-expanded="true">▾</button>'
    # 子を足せるのは「フォルダの単位」だけ（親はフォルダで表すので、ファイル 1 つの単位の下には置けない）。
    can_add = editable and row.path is not None and row.path.name == "item.md"
    add = (
        f'<button class="add" type="button" data-ref="{_esc(row.ref)}" title="この下に作業を足す">＋</button>'
        if can_add
        else ""
    )
    cells = [
        f'<td class="code">{toggle if row.children else ""}{add}{_esc(row.code)}</td>',
        _cell("name", name, row.name, row, fields, digest, css="name"),
        _cell("team", _esc(row.team), row.team or "", row, fields, digest, css="who"),
        _cell("assignees", _esc("、".join(row.assignees)), "、".join(row.assignees), row, fields, digest, css="who"),
        _cell("status", _esc(status_label), row.status.value if row.status else "", row, fields, digest, css="st"),
        _cell("start", _day_label(row.start), row.start.isoformat() if row.start else "", row, fields, digest, css="d"),
        _cell("due", _day_label(row.due), row.due.isoformat() if row.due else "", row, fields, digest, css="d"),
        f'<td class="n">{"" if row.workdays is None else row.workdays}</td>',
        f'<td class="d">{_day_label(row.actual_start)}</td>',
        f'<td class="d">{_day_label(row.actual_finish)}</td>',
        f'<td class="n">{f"{row.done_leaves}/{row.total_leaves}" if row.total_leaves else ""}</td>',
        f'<td class="gantt">{_bar_svg(row, span, today) if span else ""}</td>',
    ]
    return f'<tr class="{" ".join(classes)}" data-code="{_esc(row.code)}">{"".join(cells)}</tr>'


def _digest_of(row: WbsRow) -> str:
    """その行の値が入っているファイルの指紋（保存時の競合検出に使う）。"""
    from harness.deliver.editor import file_digest

    return file_digest(row.path) if row.path is not None else ""


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
/* 罫線はセルの右下だけに引く（sticky を効かせるため collapse を使わない）。 */
table { border-collapse:separate; border-spacing:0; width:100%; min-width:900px; }
thead { display:table-header-group; }
th, td { border-right:1px solid var(--line); border-bottom:1px solid var(--line);
         padding:2px 5px; vertical-align:middle; white-space:nowrap; }
thead th { border-top:1px solid var(--line); }
th:first-child, td:first-child { border-left:1px solid var(--line); }
th { background:var(--sec); font-weight:600; font-size:11px; text-align:left; }
tr { break-inside:avoid; }
/* 左の表は必要な幅まで詰める＝いちばん見せたいガントが画面外へ押し出されないようにする。 */
th.code, td.code { width:42px; color:var(--muted); font-variant-numeric:tabular-nums; }
th.who, td.who { width:74px; overflow:hidden; text-overflow:ellipsis; }
th.st, td.st { width:46px; }
th.d, td.d { width:46px; }
th.n, td.n { width:34px; }
td.d, td.n { text-align:right; font-variant-numeric:tabular-nums; font-size:11px; }
th.name, td.name { white-space:normal; min-width:150px; }
th.gantt, td.gantt { width:40%; min-width:280px; padding:0 2px; }
/* 横に溢れたときも、どの作業の棒かが分かるように WBS 番号と作業名を左へ貼り付ける。 */
th.code, td.code, th.name, td.name { position:sticky; z-index:2; background:var(--paper); }
th.code, td.code { left:0; }
th.name, td.name { left:42px; }
thead th.code, thead th.name { z-index:3; background:var(--sec); }
tr.lv0 > td.code, tr.lv0 > td.name { background:var(--sec); }
.ref { color:var(--muted); font-size:10px; margin-left:6px; }
.tag { background:var(--tag-bg); color:var(--tag-ink); font-size:10px; padding:0 4px; margin-left:6px;
       border-radius:2px; }
tr.lv0 > td { background:var(--sec); font-weight:600; }
tr.lv1 td.name { padding-left:18px; }
tr.lv2 td.name { padding-left:34px; }
tr.lv3 td.name { padding-left:50px; }
tr.is-late td.d, tr.is-late td.name { color:var(--late-ink); }
/* 完了した行は落ち着かせる（残っている作業が目に入るように）。取り消し線は付けない＝実績の日付は読ませたい。 */
tr.is-done > td { color:var(--muted); }
tr.is-done rect.done { opacity:.55; }
.ops { display:flex; gap:6px; align-items:center; margin-top:6px; flex-wrap:wrap; }
.ops button { font:inherit; font-size:11px; color:var(--ink); background:var(--paper); cursor:pointer;
              border:1px solid var(--line); border-radius:3px; padding:1px 8px; }
.ops button:hover { background:var(--sec); }
button.add { border:0; background:none; color:var(--plan); font:inherit; cursor:pointer; padding:0 3px 0 0; }
button.add:hover { text-decoration:underline; }
svg.bar, svg.axis { display:block; width:100%; height:14px; }
svg.axis line { stroke:var(--line); stroke-width:1; }
.axis-wrap { position:relative; height:14px; }
.axis-lab { position:absolute; top:0; margin-left:2px; font-size:8px; font-weight:400; color:var(--muted);
            white-space:nowrap; line-height:1; }
rect.plan { fill:var(--plan); } rect.done { fill:var(--done); } rect.late { fill:var(--late); }
rect.prog { fill:var(--prog); opacity:.75; } polygon.ms { fill:var(--ink); }
line.today { stroke:var(--today); stroke-width:1.2; stroke-dasharray:2 2; }
footer { margin-top:14px; font-size:11px; color:var(--muted); }
footer h2 { font-size:12px; color:var(--ink); margin:10px 0 4px; }
.legend span { margin-right:14px; }
.legend i { display:inline-block; width:16px; height:8px; border-radius:2px; vertical-align:middle; margin-right:4px; }
tr.hid { display:none; }
button.tw { border:0; background:none; color:var(--muted); font:inherit; cursor:pointer; padding:0 4px 0 0;
            line-height:1; }
button.tw:focus-visible { outline:2px solid var(--plan); outline-offset:1px; }
@media print {
  /* 畳んだ行も必ず刷る（畳んだまま印刷して白紙のフェーズを渡す事故を、CSS の段階で起こらなくする）。 */
  tr.hid { display:table-row !important; }
  button.tw { display:none; }
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
  /* 紙では貼り付けが効かない（かえって重なる）ので普通の列に戻す。 */
  th.code, td.code, th.name, td.name { position:static; }
  /* 操作のボタンは紙に出さない。 */
  .ops, button.add { display:none; }
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


_EDIT_STYLE = """
td.edit { cursor:text; }
td.edit:hover { background:color-mix(in srgb, var(--plan) 14%, transparent); }
td.edit:focus-visible { outline:2px solid var(--plan); outline-offset:-2px; }
td.edit .blank { color:var(--muted); opacity:.45; }
td.edit input, td.edit select { width:100%; font:inherit; color:var(--ink); background:var(--paper);
                               border:1px solid var(--plan); border-radius:2px; padding:1px 3px; }
#say { position:fixed; left:50%; bottom:18px; transform:translateX(-50%); max-width:min(720px,92vw);
       background:var(--ink); color:var(--paper); padding:8px 14px; border-radius:4px; font-size:12px;
       line-height:1.5; box-shadow:0 6px 24px rgba(0,0,0,.28); display:none; z-index:9; }
#say.bad { background:var(--late-ink); }
.hint { color:var(--muted); font-size:11px; }
"""

# 折りたたみ（閲覧・編集の両方に付く）。行を DOM から消さずに隠すだけにして、印刷では CSS が必ず戻す
# ＝畳んだまま刷って白紙のフェーズを渡す事故が、そもそも起こらない形にする。
_VIEW_SCRIPT = """
(function(){
  function toggles(){ return document.querySelectorAll('.tw'); }
  function setAll(open){
    toggles().forEach(function(b){ b.setAttribute('aria-expanded', open?'true':'false');
                                   b.textContent = open?'▾':'▸'; });
    document.querySelectorAll('tr[data-code]').forEach(function(tr){
      if(tr.dataset.code.indexOf('.')<0) return;         // 第 1 階層は常に見せる
      tr.classList.toggle('hid', !open);
    });
  }
  var fold=document.getElementById('fold'), unfold=document.getElementById('unfold');
  if(fold) fold.addEventListener('click', function(){ setAll(false); });
  if(unfold) unfold.addEventListener('click', function(){ setAll(true); });
  function hidden(code){
    var shut=document.querySelectorAll('.tw[aria-expanded="false"]');
    for(var i=0;i<shut.length;i++){
      var c=shut[i].dataset.code;
      if(code!==c && code.indexOf(c+'.')===0) return true;
    }
    return false;
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest && e.target.closest('.tw'); if(!b) return;
    var open=b.getAttribute('aria-expanded')==='true';
    b.setAttribute('aria-expanded', open?'false':'true');
    b.textContent = open?'▸':'▾';
    var code=b.dataset.code, rows=document.querySelectorAll('tr[data-code]');
    for(var i=0;i<rows.length;i++){
      var c=rows[i].dataset.code;
      if(c===code || c.indexOf(code+'.')!==0) continue;
      if(open) rows[i].classList.add('hid');
      else if(!hidden(c)) rows[i].classList.remove('hid');
    }
  });
})();
"""

# 保存に成功したら画面を作り直す（部分更新しない）。日数・ロールアップ・進捗・遅れは導出値なので、
# 1 か所直すと他の行の値も動く。画面側で導出をやり直すと計算が 2 か所になるため、再読込で全部やり直す。
_EDIT_SCRIPT = """
(function(){
  var token=document.currentScript.dataset.token, say=document.getElementById('say'), busy=false;
  function tell(msg,bad){ say.textContent=msg; say.className=bad?'bad':''; say.style.display='block';
    if(!bad) setTimeout(function(){ say.style.display='none'; },1600); }
  function send(td,value){
    if(busy) return; busy=true;
    fetch('edit',{method:'POST',headers:{'Content-Type':'application/json','X-WBS-Token':token},
      body:JSON.stringify({ref:td.dataset.ref,field:td.dataset.field,value:value,base:td.dataset.base})})
      .then(function(r){ return r.json().then(function(b){ return {ok:r.ok,body:b}; }); })
      .then(function(r){ if(r.ok){ tell('保存した'); location.reload(); }
                         else { busy=false; tell(r.body.detail||'保存できなかった',true); } })
      .catch(function(e){ busy=false; tell('保存できなかった: '+e,true); });
  }
  function open(td){
    if(td.querySelector('input,select')) return;
    var old=td.dataset.value, box;
    if(td.dataset.field==='status'){
      box=document.createElement('select');
      ['todo','in-progress','in-review','blocked','done'].forEach(function(v){
        var o=document.createElement('option'); o.value=v; o.textContent=v; box.appendChild(o); });
      box.value=old;
    } else {
      box=document.createElement('input');
      box.type=(td.dataset.field==='start'||td.dataset.field==='due')?'date':'text';
      box.value=old;
    }
    td.textContent=''; td.appendChild(box); box.focus();
    var done=false;
    function commit(){ if(done) return; done=true;
      if(box.value===old){ location.reload(); return; } send(td,box.value); }
    function cancel(){ if(done) return; done=true; location.reload(); }
    box.addEventListener('blur',commit);
    box.addEventListener('change',function(){ if(box.tagName==='SELECT') commit(); });
    box.addEventListener('keydown',function(e){
      if(e.key==='Enter'){ e.preventDefault(); commit(); } if(e.key==='Escape'){ cancel(); } });
  }
  function add(parent){
    if(busy) return; busy=true;
    fetch('add',{method:'POST',headers:{'Content-Type':'application/json','X-WBS-Token':token},
      body:JSON.stringify({parent:parent})})
      .then(function(r){ return r.json().then(function(b){ return {ok:r.ok,body:b}; }); })
      .then(function(r){ if(r.ok){ tell('足した: '+r.body.id); location.reload(); }
                         else { busy=false; tell(r.body.detail||'足せなかった',true); } })
      .catch(function(e){ busy=false; tell('足せなかった: '+e,true); });
  }
  document.addEventListener('click',function(e){
    var plus=e.target.closest && e.target.closest('button.add');
    if(plus){ e.preventDefault(); add(plus.dataset.ref); return; }
    var top=e.target.closest && e.target.closest('#addtop');
    if(top){ e.preventDefault(); add(null); return; }
    var td=e.target.closest && e.target.closest('td.edit'); if(td) open(td); });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter') return;
    var td=document.activeElement;
    if(td&&td.classList&&td.classList.contains('edit')){ e.preventDefault(); open(td); } });
})();
"""


# 完全な文書として出す（断片で渡さない）。文字コードの宣言が無いと、受け手のブラウザの設定次第で
# 日本語が化ける（提出先の環境は制御できない）。doctype が無いと後方互換モードで描画され、印刷時の
# 文字寸法の指定が表に効かず A3 に収まる前提が崩れる。題は印刷のヘッダにも出る。
_DOCUMENT = (
    '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    "<title>{title}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
)


def render_html(wbs: Wbs, *, provenance: str = "", draft: bool = False, editable: bool = False, token: str = "") -> str:
    """WBS 一式を完全な HTML 文書 1 つに描く。閲覧用と編集用で同じ描き方を使う。

    `provenance` は生成物の由来（どのコミット・いつ・どの木から出たか）を 1 行で表した文字列。
    `draft` を立てると下書きと分かる表示にする（未コミットの変更を含む生成物を、そうと分かる形でだけ許す）。
    `editable` を立てると、直せる欄に書き戻し先の目印と入力の仕掛けが付く（編集サーバから配るときだけ）。
    ファイルに書き出す生成物は常に `editable=False`＝保存の口が無いので、渡した先で編集はできない。
    """
    span = wbs.span
    head = "".join(f'<th class="{css}">{_esc(label)}</th>' for label, css in COLUMNS)
    axis = f'<th class="gantt">{_axis_svg(span, wbs.today) if span else ""}</th>'
    body = "".join(_row_html(row, span, wbs.today, editable=editable) for row in wbs.walk())
    title = wbs.overlay.project or "WBS"
    client = f"<div>提出先: {_esc(wbs.overlay.client)}</div>" if wbs.overlay.client else ""
    unscheduled = wbs.unscheduled
    notes = ""
    if unscheduled:
        ids = "、".join(_esc(r.ref or r.name) for r in unscheduled)
        notes = f"<h2>未日程（{len(unscheduled)} 件）</h2><p>予定を置いていない作業: {ids}</p>"
    period = f"　期間 {span[0].isoformat()} 〜 {span[1].isoformat()}" if span else ""
    banner = '<div class="meta" style="color:var(--late-ink)">下書き（未コミットの変更を含む）</div>' if draft else ""
    ops = ['<button id="fold" type="button">全部閉じる</button>', '<button id="unfold" type="button">全部展開</button>']
    if editable:
        ops.append('<button id="addtop" type="button">＋ 最上位に作業を足す</button>')
    edit_bits = ""
    if editable:
        banner += (
            '<div class="hint">セルをクリックすると直せる（Enter で保存・Esc で取り消し）。'
            "書き戻す先は正本（作業単位の frontmatter と docs/wbs.yaml）。導出される値に編集の口は無い。</div>"
        )
        edit_bits = f'<div id="say"></div><script data-token="{_esc(token)}">{_EDIT_SCRIPT}</script>'
    inner = (
        f"<style>{_STYLE}{_EDIT_STYLE if editable else ''}</style>"
        f"<header><h1>{_esc(title)}</h1>{client}"
        f'<div class="meta">基準日 {wbs.today.isoformat()}{period}　{_esc(provenance)}</div>{banner}'
        f'<div class="ops">{"".join(ops)}</div></header>'
        f'<div class="scroll"><table><thead><tr>{head}{axis}</tr></thead><tbody>{body}</tbody></table></div>'
        f"<footer>{_legend()}{notes}</footer><script>{_VIEW_SCRIPT}</script>{edit_bits}"
    )
    return _DOCUMENT.format(title=_esc(title), body=inner)
