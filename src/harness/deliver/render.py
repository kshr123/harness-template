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
import json
from collections.abc import Callable
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

# 表の列（見出し・幅と寄せを決める区分・意味のまとまり）。見出しの並びは形式に依らないので、表計算もここから引く。
# **まとまりごとに見出しをもう 1 段置く**（作業／予定／実績）。11 列が同じ重みで並んでいると、どこまでが
# 予定でどこからが実績なのかを列名だけで読み分けることになる。まとまりの先頭には強い縦罫（`gs`）を引く。
COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("No.", "code", "work"),
    ("作業", "name", "work"),
    ("チーム", "team", "work"),
    ("担当", "who", "work"),
    ("状態", "st", "work"),
    ("予定開始", "d gs", "plan"),
    ("予定終了", "d", "plan"),
    ("日数", "n", "plan"),
    ("実績開始", "d gs", "act"),
    ("実績終了", "d", "act"),
    ("進捗", "n", "act"),
)

# まとまりの見出し（列の意味を 1 段上でまとめる）。
COLUMN_GROUPS: tuple[tuple[str, str], ...] = (("work", "作業"), ("plan", "予定"), ("act", "実績"))

COLUMN_LABELS: tuple[str, ...] = tuple(label for label, _, _ in COLUMNS)

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


# 日の目盛を出す上限（これを超えると 1 行あたりの図形が増えすぎてファイルが太る）。
_MAX_DAY_TICKS = 400


def drawing_window(span: tuple[date, date]) -> tuple[date, date]:
    """図を描く期間。データの期間を**月の境目に合わせて広げる**（1 日始まり・月末終わり）。

    月に揃えるのは、日を数字で並べたときに「1 から月末まで」になるため（途中の日から始まると、
    何月の何日を見ているのか読みにくい）。月の見出しの区切りとも位置が合う。データの期間をそのまま使うと、
    数日しかない案件で棒が列の端から端まで伸びて「ただの帯」になる、という問題もこれで解ける
    （1 か月は必ず 28 日以上あるため）。
    """
    first, last = span
    first = first.replace(day=1)
    last = _month_end(last)
    return first, last


def _month_end(day: date) -> date:
    """その月の末日。"""
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def backdrop(span: tuple[date, date], today: date) -> str:
    """全行に共通の下敷き（時間軸の格子・今日の線）。

    棒だけを描くと図表に見えない（時間の目盛が無いので、棒の長さが何日なのか読めない）。格子は軸の目盛と
    同じ位置に引く＝上の見出しと目で繋がる。週の区切りは格子線で、営業日の数は「日数」の列で分かるので、
    非稼働日の帯は敷かない（各週の右に灰色が並んで棒より目立ってしまうため）。
    """
    first, last = span
    scale = _CANVAS / ((last - first).days + 1)
    parts: list[str] = []
    for kind, ticks in (("d", day_ticks(span)), ("w", week_ticks(span)), ("m", month_ticks(span))):
        if kind == "d" and (last - first).days + 1 > _MAX_DAY_TICKS:
            continue
        for tick in ticks:
            if tick == first:  # 先頭は列の左端なので線を引かない
                continue
            x = _x_of(tick, span)
            parts.append(
                f'<line class="grid g-{kind}" x1="{x:.2f}" y1="0" x2="{x:.2f}" y2="14"'
                f' vector-effect="non-scaling-stroke" />'
            )
    if first <= today <= last:
        tx = _x_of(today, span) + scale / 2
        parts.append(
            f'<line class="today" x1="{tx:.2f}" y1="0" x2="{tx:.2f}" y2="14" vector-effect="non-scaling-stroke" />'
        )
    return "".join(parts)


def _bar_svg(row: WbsRow, span: tuple[date, date], back: str) -> str:
    """1 行分のガント（その行のセルに収まる小さな SVG）＝共通の下敷き＋その行の棒。"""
    first, last = span
    scale = _CANVAS / ((last - first).days + 1)
    parts: list[str] = [
        f'<svg class="bar" viewBox="0 0 {_CANVAS:.0f} 14" preserveAspectRatio="none" role="img">',
        back,
    ]
    if row.milestone and row.due is not None:
        pass  # 節目は図形を引き伸ばすと潰れるので、SVG でなく割合の位置に置く HTML で描く（_milestone）
    elif row.start is not None and row.due is not None:
        x = _x_of(row.start, span)
        width = max(_x_of(row.due, span) + scale - x, 2.0)
        if row.children:
            # まとめの行（節・子を持つ単位）は、末端の棒と同じ太さで塗らない。全部同じ太さの帯が並ぶと
            # 階層が図から読めず「ただの帯」に見える。工程表の慣習どおり、細い帯と両端の脚で表す。
            parts.append(f'<rect class="sum" x="{x:.2f}" y="2" width="{width:.2f}" height="4" />')
            for leg in (x, x + width):
                parts.append(
                    f'<line class="leg" x1="{leg:.2f}" y1="2" x2="{leg:.2f}" y2="11"'
                    f' vector-effect="non-scaling-stroke" />'
                )
        else:
            parts.append(f'<rect class="bar" x="{x:.2f}" y="3" width="{width:.2f}" height="8" />')
    parts.append("</svg>")
    return "".join(parts)


def day_ticks(span: tuple[date, date]) -> list[date]:
    """日の目盛（1 日ごと）。"""
    first, last = span
    out: list[date] = []
    day = first
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def week_ticks(span: tuple[date, date]) -> list[date]:
    """週の目盛（月曜）。期間の頭は必ず入れる。"""
    first, last = span
    out: list[date] = []
    day = first - timedelta(days=first.weekday())
    while day <= last:
        if day >= first:
            out.append(day)
        day += timedelta(days=7)
    if not out or out[0] != first:
        out = [first, *out]
    return out


def month_ticks(span: tuple[date, date]) -> list[date]:
    """月の目盛（月の頭）。期間の頭は必ず入れる。"""
    first, last = span
    out: list[date] = []
    year, month = first.year, first.month
    while True:
        current = date(year, month, 1)
        if current > last:
            break
        if current >= first:
            out.append(current)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    if not out or out[0] != first:
        out = [first, *out]
    return out


def year_ticks(span: tuple[date, date]) -> list[date]:
    """年の目盛（年の頭）。期間の頭は必ず入れる。"""
    first, last = span
    out = [date(y, 1, 1) for y in range(first.year, last.year + 1) if date(y, 1, 1) >= first]
    if not out or out[0] != first:
        out = [first, *out]
    return out


def _intervals(ticks: list[date], span: tuple[date, date]) -> list[tuple[date, float, float]]:
    """目盛を「区間」にする（その日・左端の割合・幅の割合）。ラベルは区間の真ん中に置く。

    目盛の線の右に文字を寄せると、どの線の分の文字なのかが読めない。区間の中央に置けば対応が一目で分かる。
    """
    first, last = span
    total = (last - first).days + 1
    out: list[tuple[date, float, float]] = []
    for i, tick in enumerate(ticks):
        nxt = ticks[i + 1] if i + 1 < len(ticks) else last + timedelta(days=1)
        left = (tick - first).days / total * 100
        width = (nxt - tick).days / total * 100
        out.append((tick, left, width))
    return out


def _labels(
    ticks: list[date],
    span: tuple[date, date],
    kind: str,
    text: Callable[[date, bool], str],
    *,
    min_days: int = 0,
) -> str:
    """区間の真ん中に置くラベルの並び（年が変わるところだけ年を添える）。

    `min_days` より短い区間にはラベルを置かない。月の頭で切れた半端な週などは、置いても文字が途中で
    切れて読めない（`8/` のように見える）ので、線だけ残して文字は出さない。
    """
    parts: list[str] = []
    shown_year: int | None = None
    total = (span[1] - span[0]).days + 1
    for day, left, width in _intervals(ticks, span):
        if width / 100 * total < min_days:
            shown_year = day.year
            continue
        label = text(day, day.year != shown_year)
        shown_year = day.year
        parts.append(f'<span class="axis-lab lab-{kind}" style="left:{left:.3f}%;width:{width:.3f}%">{label}</span>')
    return "".join(parts)


_WD = "月火水木金土日"


def _weekdays(span: tuple[date, date]) -> str:
    """曜日のラベル（日表示のときだけ出す 3 段目）。土日は薄くする。"""
    parts: list[str] = []
    for day, left, width in _intervals(day_ticks(span), span):
        weekend = " we" if day.weekday() >= 5 else ""
        parts.append(
            f'<span class="axis-lab lab-wd{weekend}" style="left:{left:.3f}%;width:{width:.3f}%">'
            f"{_WD[day.weekday()]}</span>"
        )
    return "".join(parts)


def _axis_svg(span: tuple[date, date], today: date) -> str:
    """時間軸の見出し（2 段）。上段＝大きい単位・下段＝選んだ単位。

    単位（月・週・日）を切り替えると**下段の中身が変わり、上段はその親の単位になる**。段数は常に 2 で
    固定する（切り替えのたびに高さが跳ねない）。線は SVG・文字は HTML の要素で、どちらも同じ割合の座標に
    乗せる（引き伸ばしても文字が潰れない）。
    """
    first, last = span
    days = (last - first).days + 1
    ticks = f'<svg class="axis" viewBox="0 0 {_CANVAS:.0f} 40" preserveAspectRatio="none" role="img">'
    lines: list[str] = []
    for kind, series in (("d", day_ticks(span)), ("w", week_ticks(span)), ("m", month_ticks(span))):
        if kind == "d" and days > _MAX_DAY_TICKS:
            continue
        for tick in series:
            if tick == first:
                continue
            x = _x_of(tick, span)
            lines.append(
                f'<line class="g-{kind}" x1="{x:.2f}" y1="0" x2="{x:.2f}" y2="40" vector-effect="non-scaling-stroke" />'
            )
    if first <= today <= last:
        tx = _x_of(today, span) + _CANVAS / days / 2
        lines.append(
            f'<line class="today" x1="{tx:.2f}" y1="0" x2="{tx:.2f}" y2="40" vector-effect="non-scaling-stroke" />'
        )
    text = "".join(
        (
            _labels(year_ticks(span), span, "y", lambda d, _: f"{d.year}年", min_days=40),
            _labels(month_ticks(span), span, "m", lambda d, _: f"{d.month}月", min_days=10),
            _labels(
                month_ticks(span),
                span,
                "my",
                lambda d, y: f"{d.year}年{d.month}月" if y else f"{d.month}月",
                min_days=10,
            ),
            _labels(week_ticks(span), span, "w", lambda d, _: f"{d.month}/{d.day}w", min_days=4),
            _labels(day_ticks(span), span, "d", lambda d, _: str(d.day)) if days <= _MAX_DAY_TICKS else "",
            _weekdays(span) if days <= _MAX_DAY_TICKS else "",
        )
    )
    return f'<div class="axis-wrap">{ticks}{"".join(lines)}</svg>{text}</div>'


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
    fields["team"] = "team"
    fields["assignees"] = "assignees" if manual else "owner"
    return fields


def _cell(
    column: str,
    inner: str,
    raw: str,
    row: WbsRow,
    fields: dict[str, str],
    digest: str,
    *,
    css: str = "",
    choices: list[str] | None = None,
) -> str:
    """1 つのセル。直せる欄なら、書き戻し先（ID・キー・読んだ時点の指紋）を持たせる。

    `choices` を渡した欄は、自由入力でなく**名簿から選ぶ**（毎回打つと表記ゆれが起きるため）。
    名簿に無い名前を入れる口も残し、入れたらその名簿にも足す。
    """
    field = fields.get(column)
    klass = f' class="{css}"' if css else ""
    if field is None or row.ref is None:
        return f"<td{klass}>{inner}</td>"
    picks = f' data-choices="{_esc(json.dumps(choices, ensure_ascii=False))}"' if choices is not None else ""
    attrs = (
        f' class="edit{" " + css if css else ""}" data-ref="{_esc(row.ref)}" data-field="{_esc(field)}"'
        f' data-value="{_esc(raw)}" data-base="{_esc(digest)}"{picks}'
    )
    return f'<td{attrs} tabindex="0">{inner or '<span class="blank">＋</span>'}</td>'


def _row_html(
    row: WbsRow,
    span: tuple[date, date] | None,
    today: date,
    back: str = "",
    *,
    editable: bool = False,
    rosters: dict[str, list[str]] | None = None,
    parent: str = "",
) -> str:
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
    if row.ref and row.ref != row.name:  # 題を書いていない単位は ID がそのまま名前なので、2 回出さない
        name += f'<span class="ref">{_esc(row.ref)}</span>'
    fields = _editable_fields(row) if editable else {}
    digest = _digest_of(row) if fields else ""
    names = rosters or {"teams": [], "members": []}
    status_label = STATUS_LABEL[row.status] if row.status is not None else ""
    # 折りたたみの取っ手は WBS 番号の列に置く（表題の列は直せる欄なので、押すたびに編集が始まってしまう）。
    toggle = f'<button class="tw" type="button" data-code="{_esc(row.code)}" aria-expanded="true">▾</button>'
    # 下の階層はどの作業単位にも足せる（ファイル 1 つの単位は、足すときにフォルダの単位へ変わる＝分解）。
    can_add = editable and row.source == "work" and row.ref is not None
    cells = [
        f'<td class="code">{toggle if row.children else ""}{_esc(row.code)}</td>',
        _cell("name", name, row.name, row, fields, digest, css="name"),
        _cell("team", _esc(row.team), row.team or "", row, fields, digest, css="team", choices=names["teams"]),
        _cell(
            "assignees",
            _esc("、".join(row.assignees)),
            "、".join(row.assignees),
            row,
            fields,
            digest,
            css="who",
            choices=names["members"],
        ),
        _cell("status", _esc(status_label), row.status.value if row.status else "", row, fields, digest, css="st"),
        _cell(
            "start", _day_label(row.start), row.start.isoformat() if row.start else "", row, fields, digest, css="d gs"
        ),
        _cell("due", _day_label(row.due), row.due.isoformat() if row.due else "", row, fields, digest, css="d"),
        f'<td class="n">{"" if row.workdays is None else row.workdays}</td>',
        f'<td class="d gs">{_day_label(row.actual_start)}</td>',
        f'<td class="d">{_day_label(row.actual_finish)}</td>',
        f'<td class="n">{f"{row.done_leaves}/{row.total_leaves}" if row.total_leaves else ""}</td>',
        f'<td class="gantt">{_bar_svg(row, span, back) if span else ""}{_milestone(row, span)}</td>',
    ]
    holder = _esc(row.ref) if can_add else ""
    return (
        f'<tr class="{" ".join(classes)}" data-code="{_esc(row.code)}" data-ref="{_esc(row.ref or "")}"'
        f' data-name="{_esc(row.name)}" data-level="{depth + 1}" data-kids="{1 if row.children else 0}"'
        f' data-holder="{holder}" data-parent="{_esc(parent)}">{"".join(cells)}</tr>'
    )


def _holders(rows: list[WbsRow], holder: str) -> dict[str, str]:
    """各行の「同じ階層に足すときの足し先」（＝いちばん近い、子を置けるフォルダの単位）を集める。

    右クリックの「同じ階層に作業を足す」がどこへ足すかを、画面側で組み立て直さないための対応。
    """
    out: dict[str, str] = {}
    for row in rows:
        out[row.code] = holder
        mine = row.ref if row.source == "work" and row.ref else holder
        out.update(_holders(row.children, mine))
    return out


def _view_script() -> str:
    """閲覧の仕掛け（まとまりごとの列数を JS に渡す）。"""
    sizes = {key: sum(1 for _, _, group in COLUMNS if group == key) for key, _ in COLUMN_GROUPS}
    return _VIEW_SCRIPT.replace("__COLS__", json.dumps(sizes))


def _milestone_row(wbs: Wbs, span: tuple[date, date] | None) -> str:
    """ガントの最上部に置く「マイルストーン」の集約行。全マイルストーン（◆）を時間軸に並べる。

    各フェーズに散らばる◆だけだと、案件全体の節目（要件確定・検収・定例など）を一目で追えない。
    工程表の慣習どおり、上部に節目だけの帯を 1 本置く。マイルストーンが 1 つも無ければ行を出さない。
    """
    if span is None:
        return ""
    marks = [r for r in wbs.walk() if r.milestone and r.due is not None]
    if not marks:
        return ""
    first, last = span
    total = (last - first).days + 1
    diamonds = "".join(
        f'<span class="ms" style="left:{((r.due - first).days + 0.5) / total * 100:.3f}%" '
        f'title="{_esc(r.name)}（{r.due.isoformat()}）">◆</span>'
        for r in marks
        if r.due is not None and first <= r.due <= last
    )
    n_cols = len(COLUMNS)
    return (
        '<tr class="msrow">'
        f'<td class="ms-label" colspan="{n_cols}">マイルストーン</td>'
        f'<td class="gantt ms-track">{diamonds}</td></tr>'
    )


def _milestone(row: WbsRow, span: tuple[date, date] | None) -> str:
    """節目の印。引き伸ばす図形の中に置くと横に潰れるので、割合の位置に重ねる要素として描く。"""
    if span is None or not row.milestone or row.due is None:
        return ""
    first, last = span
    total = (last - first).days + 1
    left = ((row.due - first).days + 0.5) / total * 100
    return f'<span class="ms" style="left:{left:.3f}%">◆</span>'


def _digest_of(row: WbsRow) -> str:
    """その行の値が入っているファイルの指紋（保存時の競合検出に使う）。"""
    from harness.deliver.editor import file_digest

    return file_digest(row.path) if row.path is not None else ""


# 色は 3 色まで（白・黒・青）＋警告の 1 色（赤）。濃さは変えてよいので、黒は 5 段・青は 3 段・赤は 2 段で作る。
# **＋1 色を赤にした理由**：顧客向けの工程表で読み落とすと実害が出るのは「遅れ」だけで、警告は赤以外に代えが
# きかない。完了は状態の列・実績の日付・進捗の数・棒の淡さで 4 重に表しているので、色相に頼らなくてよい。
# 罫線は重みを 3 段に分ける（弱＝行の区切りと日/週の格子／強＝見出しの下端・月の格子・貼り付く列の右／
# 2px＝表とガントの領域の境目）。すべて同じ太さで引くと表計算の初期状態に見える。
_STYLE = """
:root {
  --paper:#ffffff; --sec:#eef1f5; --hover:#f2f6fb; --sel:#e7f0fa;
  --line:#e3e6ea; --line-strong:#86919e;
  --ink:#1f242b; --muted:#5b6470; --sum:#3f454d;
  --plan:#3e80c4; --done:#a8c6e3; --prog:#163e69;
  --late:#b12f1f; --late-ink:#963627; --today:#b12f1f;
  --tag-bg:#f5edeb; --tag-ink:#963627; --done-row:#ebf0f5; --late-row:#f5edeb;
  --bar:#7ba3cf; --bar-done:#2f6099;
  --btn-on-bg:#163e69; --btn-on-ink:#ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
  --paper:#15181d; --sec:#20252c; --hover:#242b34; --sel:#223349;
  --line:#2e343c; --line-strong:#5b6672;
  --ink:#e7eaee; --muted:#9aa4b0; --sum:#b6bec7;
  --plan:#5f9ede; --done:#456c96; --prog:#aecff2;
  --late:#e26a58; --late-ink:#e8a094; --today:#e26a58;
  --tag-bg:#282120; --tag-ink:#e8a094; --done-row:#1f2328; --late-row:#282120;
  --bar:#48699a; --bar-done:#9cc3ec;
  --btn-on-bg:#5f9ede; --btn-on-ink:#0d1b2a;
  }
}
:root[data-theme="dark"] {
  --paper:#15181d; --sec:#20252c; --hover:#242b34; --sel:#223349;
  --line:#2e343c; --line-strong:#5b6672;
  --ink:#e7eaee; --muted:#9aa4b0; --sum:#b6bec7;
  --plan:#5f9ede; --done:#456c96; --prog:#aecff2;
  --late:#e26a58; --late-ink:#e8a094; --today:#e26a58;
  --tag-bg:#282120; --tag-ink:#e8a094; --done-row:#1f2328; --late-row:#282120;
  --bar:#48699a; --bar-done:#9cc3ec;
  --btn-on-bg:#5f9ede; --btn-on-ink:#0d1b2a;
}
:root[data-theme="light"] {
  --paper:#ffffff; --sec:#eef1f5; --hover:#f2f6fb; --sel:#e7f0fa;
  --line:#e3e6ea; --line-strong:#86919e;
  --ink:#1f242b; --muted:#5b6470; --sum:#3f454d;
  --plan:#3e80c4; --done:#a8c6e3; --prog:#163e69;
  --late:#b12f1f; --late-ink:#963627; --today:#b12f1f;
  --tag-bg:#f5edeb; --tag-ink:#963627; --done-row:#ebf0f5; --late-row:#f5edeb;
  --bar:#7ba3cf; --bar-done:#2f6099;
  --btn-on-bg:#163e69; --btn-on-ink:#ffffff;
}
* { box-sizing:border-box; }
body { margin:0; padding:20px 24px; color:var(--ink); background:var(--paper);
       font:13px/1.45 "Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif; }
header { border-bottom:2px solid var(--ink); padding-bottom:8px; margin-bottom:12px; }
h1 { font-size:16px; font-weight:700; letter-spacing:.01em; margin:0 0 2px; }
.meta { color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }
/* 表の外枠は入れ物 1 枚に集める（セルの外周罫を撤去＝方眼に見えないようにする）。 */
.scroll { overflow:auto; max-height:calc(100vh - 150px); border:1px solid var(--line); border-radius:8px;
          container-type:scroll-state; }
table { border-collapse:separate; border-spacing:0; width:max-content; min-width:100%; }
thead { display:table-header-group; }
thead th { position:sticky; top:0; z-index:4; border-top:0; border-bottom:1px solid var(--line-strong); }
/* 見出しは 2 段（上＝列の意味のまとまり・下＝列名）。ガントは 2 段ぶちぬきで、時間軸の 2 段と高さが揃う。 */
.grp th { height:22px; padding:0 8px; text-align:center; font-size:10px; letter-spacing:.08em;
          border-bottom:1px solid var(--line); }
thead tr:last-child th { height:22px; padding:0 8px; top:23px; }
thead th.gantt { top:0; padding:0 2px; vertical-align:top; }
/* まとまりの先頭には強い縦罫を引く（どこまでが予定でどこからが実績かを、列名を読まずに分ける）。 */
.gs { border-left:1px solid var(--line-strong) !important; }
th, td { border-right:1px solid var(--line); border-bottom:1px solid var(--line);
         padding:5px 8px; vertical-align:middle; white-space:nowrap; }
th:first-child, td:first-child { border-left:0; }
th:last-child, td:last-child { border-right:0; }
th { background:var(--sec); color:var(--muted); font-weight:600; font-size:11px;
     letter-spacing:.02em; text-align:left; }
tr { break-inside:avoid; }
th.code, td.code { width:64px; min-width:64px; color:var(--muted);
                   font-variant-numeric:tabular-nums; text-align:left; padding-left:8px; }
th.who, td.who, th.team, td.team { width:74px; overflow:hidden; text-overflow:ellipsis; }
/* 要らない列は消せる（案件によってはチームも担当も無い）。まとまりの見出しの幅は JS が数え直す。 */
.scroll.hide-team th.team, .scroll.hide-team td.team { display:none; }
.scroll.hide-who th.who, .scroll.hide-who td.who { display:none; }
th.st, td.st { width:46px; }
th.d, td.d { width:46px; }
th.n, td.n { width:34px; }
td.d, td.n { text-align:right; font-variant-numeric:tabular-nums; font-size:11px; }
th.d, th.n { text-align:right; }
th.name, td.name { white-space:normal; min-width:150px; }
/* 左の表（セルの格子）とガント（時間の格子）は別の領域。2px の罫・見出しの地色・格子の作法で 3 重に割る。 */
th.gantt, td.gantt { width:40%; min-width:280px; padding:0 2px; border-left:2px solid var(--line-strong); }
th:nth-last-child(2), td:nth-last-child(2) { border-right:0; }
thead th.gantt { background:var(--paper); }
/* 横に溢れたときも、どの作業の棒かが分かるように WBS 番号と作業名を左へ貼り付ける。 */
th.code, td.code, th.name, td.name { position:sticky; z-index:2; background:var(--paper); }
tbody td.code, tbody td.name { z-index:3; }
th.code, td.code { left:0; }
th.name, td.name { left:64px; border-right:1px solid var(--line-strong); }
thead th.code, thead th.name { z-index:6; background:var(--sec); }
td.name::after, th.name::after { content:""; position:absolute; top:0; bottom:-1px; right:-9px; width:8px;
  opacity:0; background:linear-gradient(to right, rgba(15,20,26,.14), transparent);
  pointer-events:none; transition:opacity .15s; }
@container scroll-state(scrollable: inline-start) { td.name::after, th.name::after { opacity:1; } }
tr.lv0 > td { background:var(--sec); font-weight:600; border-top:1px solid var(--line-strong); }
tr.lv1 td.name { padding-left:24px; }
tr.lv2 td.name { padding-left:40px; }
tr.lv3 td.name { padding-left:56px; }
tbody tr:hover > td { background:var(--hover); }
tr.is-sel > td { background:var(--sel); }
tr.is-late td.d, tr.is-late td.name { color:var(--late-ink); }
/* 状態を行の面で示す：未実施＝白（地のまま）・完了＝グレー・遅れ＝淡ピンク（明度・彩度をそろえた 3 淡色）。
   貼り付く 2 列（code・name）は不透明なので、行の色を明示的に上書きする（宣言順が効く＝background 指定の後）。 */
tr.is-done > td { color:var(--muted); background:var(--done-row); }
tr.is-done td.code, tr.is-done td.name { background:var(--done-row); }
tr.is-done.lv0 > td { background:var(--sec); }        /* 完了フェーズは節の面を保つ */
tr.is-late > td { background:var(--late-row); }
tr.is-late td.code, tr.is-late td.name { background:var(--late-row); }
tr.is-late.lv0 > td { background:var(--late-row); }   /* 遅れフェーズは淡ピンクが節に勝つ（経営で最も見る信号） */
.ref { display:none; }
.tag { background:var(--tag-bg); color:var(--tag-ink); font-size:10px; font-weight:600;
       padding:0 5px; margin-left:6px; border-radius:3px; }
/* 時間軸：2 段（上＝大きい単位・下＝選んだ単位）。段の間に横罫、区間ごとに縦罫を引く。 */
.axis-wrap { position:relative; height:44px; }
svg.axis { display:block; width:100%; height:44px; }
.axis-wrap::before { content:""; position:absolute; top:22px; left:0; right:0; border-top:1px solid var(--line); }
/* 日付は区間の**左**に寄せる（線の右すぐ＝その区間の始まりの日、と読める）。 */
.axis-lab { display:none; position:absolute; height:22px; line-height:22px; font-size:10px;
            font-variant-numeric:tabular-nums;
            color:var(--muted); text-align:left; padding-left:4px; white-space:nowrap; overflow:hidden;
            border-left:1px solid var(--line); }
.lab-y, .lab-m, .lab-my { border-left-color:var(--line-strong); color:var(--ink); }
/* 上段のラベルは地を敷いて、下位の格子線が上段を貫通しないようにする（空マスが並ぶのを消す）。 */
.lab-y, .lab-my { background:var(--paper); }
.scroll.u-m .lab-y, .scroll.u-m .lab-m { display:block; }
.scroll.u-w .lab-my, .scroll.u-w .lab-w { display:block; }
.scroll.u-d .lab-my, .scroll.u-d .lab-d, .scroll.u-d .lab-wd { display:block; }
.scroll.u-m .lab-y, .scroll.u-w .lab-my { top:0; height:22px; line-height:22px; font-size:11px; font-weight:600; }
.scroll.u-m .lab-m, .scroll.u-w .lab-w { top:22px; height:22px; line-height:22px; }
/* 日表示は 3 段（年月・日にち・曜日）。上段 22px が左見出しの段罫と 1 本に繋がる。全段とも線の右・左揃え。 */
.scroll.u-d .lab-my { top:0; height:22px; line-height:22px; font-size:11px; font-weight:600; }
.scroll.u-d .lab-d { top:22px; height:11px; line-height:11px; }
.scroll.u-d .lab-wd { top:33px; height:11px; line-height:11px; font-size:10px;
                      padding-left:4px; border-left:1px solid var(--line); }
.scroll.u-d .lab-wd.we { color:var(--muted); }
/* 3 段目の区切り線（日表示だけ）。 */
.scroll.u-d .axis-wrap::after { content:""; position:absolute; top:33px; left:0; right:0;
                                border-top:1px solid var(--line); }
/* 格子の重み：日 < 週 < 月。月の線だけが見出しから本体まで同じ濃さで縦に通る。 */
.g-d, .g-w, .g-m { display:none; }
line.g-d { stroke:var(--line); stroke-width:.5; opacity:.45; }
line.g-w { stroke:var(--line); stroke-width:1; }
line.g-m { stroke:var(--line-strong); stroke-width:1; }
.scroll.u-m .g-m, .scroll.u-w .g-w, .scroll.u-w .g-m,
.scroll.u-d .g-d, .scroll.u-d .g-w, .scroll.u-d .g-m { display:block; }
line.today { stroke:var(--ink); stroke-width:1.4; stroke-dasharray:3 3; }
/* 棒。引き伸ばすと角丸が幅ごとに歪むので角は落とす（工程表の慣習どおりの角棒）。 */
svg.bar { display:block; width:100%; height:16px; }
svg.bar rect { rx:0; }
/* ガントは 1 色（青）のベタ塗り。予定・完了・遅れを色で分けない（状態は行の面で分かる）。
   まとめ（子を持つ行）は色でなく形＝細い帯＋両端の脚で区別する。 */
rect.bar { fill:var(--bar); }
rect.sum { fill:var(--bar); }
line.leg { stroke:var(--bar); stroke-width:2; }
td.gantt { position:relative; }
.ms { position:absolute; top:50%; transform:translateY(-50%); margin-left:-4px; font-size:12px;
      color:var(--bar-done); pointer-events:none; }
.ops { display:flex; gap:6px; align-items:center; margin-top:8px; flex-wrap:wrap;
       justify-content:space-between; }
.ops .left, .ops .right { display:flex; gap:6px; align-items:center; }
.ops button { font:inherit; font-size:11px; color:var(--ink); background:var(--paper); cursor:pointer;
              border:1px solid var(--line); border-radius:6px; padding:3px 10px; }
.ops button:hover { background:var(--hover); border-color:var(--line-strong); }
.ops .sep { color:var(--muted); font-size:11px; margin-left:10px; }
.ops button.zoom { border-radius:0; margin-left:-1px; }
.ops button.zoom:first-of-type { border-radius:6px 0 0 6px; margin-left:0; }
.ops button.zoom:last-of-type { border-radius:0 6px 6px 0; }
.ops button.zoom[aria-pressed="true"], .ops button.col[aria-pressed="true"] {
  background:var(--btn-on-bg); color:var(--btn-on-ink); border-color:var(--btn-on-bg); font-weight:600; }
.ops button.col[aria-pressed="false"] { color:var(--muted); }
button.tw { border:0; background:none; color:var(--muted); font:inherit; cursor:pointer;
            padding:0 4px 0 0; line-height:1; }
button.tw:focus-visible { outline:2px solid var(--bar-done); outline-offset:1px; }
tr.hid { display:none; }
/* マイルストーンの集約行（ガント上部の帯）。左は貼り付き、右に全ての◆を時間軸で並べる。 */
tr.msrow > td { background:var(--sec); border-bottom:1px solid var(--line-strong); }
td.ms-label { position:sticky; left:0; z-index:3; background:var(--sec); font-size:11px; font-weight:600;
              color:var(--muted); letter-spacing:.02em; }
td.ms-track { position:relative; height:20px; }
td.ms-track .ms { top:50%; }
footer { margin-top:14px; font-size:11px; color:var(--muted); }
footer h2 { font-size:12px; color:var(--ink); margin:10px 0 4px; }
.legend span { margin-right:14px; }
.legend i { display:inline-block; width:16px; height:8px; vertical-align:middle; margin-right:4px; }
@media print {
  /* 畳んだ行も必ず刷る（畳んだまま印刷して白紙のフェーズを渡す事故を、CSS の段階で起こらなくする）。 */
  tr.hid { display:table-row !important; }
  button.tw { display:none; }
  /* 紙は常に明るい版に固定する（暗い地のまま刷ると読めない・インクも無駄になる）。 */
  :root {
  --paper:#ffffff; --sec:#eef1f5; --hover:#f2f6fb; --sel:#e7f0fa;
  --line:#e3e6ea; --line-strong:#86919e;
  --ink:#1f242b; --muted:#5b6470; --sum:#3f454d;
  --plan:#3e80c4; --done:#a8c6e3; --prog:#163e69;
  --late:#b12f1f; --late-ink:#963627; --today:#b12f1f;
  --tag-bg:#f5edeb; --tag-ink:#963627; --done-row:#ebf0f5; --late-row:#f5edeb;
  --bar:#7ba3cf; --bar-done:#2f6099;
  --btn-on-bg:#163e69; --btn-on-ink:#ffffff;
  }
  th, td { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  @page { size:A3 landscape; margin:8mm; }
  body { padding:0; font-size:10px; }
  .scroll { overflow:visible; max-height:none; border:1px solid var(--line-strong); border-radius:0; }
  table { min-width:0; }
  td.gantt { min-width:0; }
  /* 紙では貼り付けが効かない（かえって重なる）ので普通の列に戻す。 */
  th.code, td.code, th.name, td.name { position:static; }
  td.name::after, th.name::after { display:none; }
  /* 操作のボタンは紙に出さない。 */
  .ops { display:none; }
  /* 単位を広げたまま印刷すると紙からはみ出して右が切れるので、紙では必ず全期間を収める。 */
  .scroll th.gantt, .scroll td.gantt { width:auto !important; min-width:0 !important; }
  table { width:100%; }
}
/* 単位ごとの列幅。JS が入れる --gw をそのまま使う（棒も格子も同じ表の中で伸び縮みする）。 */
.scroll th.gantt, .scroll td.gantt { width:var(--gw,40%); min-width:var(--gw,280px); }
table { min-width:0; }
"""


def _legend() -> str:
    return (
        '<p class="legend">'
        '<span><i style="background:var(--bar)"></i>予定</span>'
        '<span><i style="background:var(--bar);box-shadow:inset 0 0 0 6px var(--bar-done)"></i>'
        "完了ぶん（濃い塗り）</span>"
        '<span><i style="background:var(--late-row);box-shadow:inset 0 0 0 1px var(--late-ink)"></i>'
        "遅れ（予定終了を過ぎて未完＝行を淡赤で示す）</span>"
        '<span><i style="background:var(--bar-done);height:4px"></i>まとめ（配下から導いた期間）</span>'
        '<span><i style="background:var(--bar-done);width:8px;height:8px;transform:rotate(45deg)"></i>節目</span>'
        "<span>破線＝基準日</span></p>"
    )


_EDIT_STYLE = """
td.edit { cursor:text; }
td.edit:hover { background:color-mix(in srgb, var(--bar-done) 14%, transparent); }
td.edit:focus-visible { outline:2px solid var(--bar-done); outline-offset:-2px; }
td.edit .blank { color:var(--muted); opacity:.45; }
td.edit input, td.edit select { width:100%; font:inherit; color:var(--ink); background:var(--paper);
                               border:1px solid var(--bar-done); border-radius:4px; padding:1px 3px; }
#say { position:fixed; left:50%; bottom:18px; transform:translateX(-50%); max-width:min(720px,92vw);
       background:var(--ink); color:var(--paper); padding:8px 14px; border-radius:4px; font-size:12px;
       line-height:1.5; box-shadow:0 6px 24px rgba(0,0,0,.28); display:none; z-index:9; }
#say.bad { background:var(--late-ink); }
.hint { color:var(--muted); font-size:11px; }
#menu { position:absolute; display:none; z-index:20; min-width:180px; padding:4px 0;
        background:var(--paper); border:1px solid var(--line); border-radius:4px;
        box-shadow:0 8px 24px rgba(15,20,26,.16); }
#menu button { display:block; width:100%; text-align:left; font:inherit; font-size:12px; color:var(--ink);
               background:none; border:0; padding:5px 14px; cursor:pointer; }
#menu button:hover { background:var(--sec); }
#menu { min-width:240px; }
#menu button { padding:6px 14px; }
#menu .mhead { display:flex; gap:8px; align-items:center; justify-content:space-between;
               padding:7px 14px 8px; border-bottom:1px solid var(--line); margin-bottom:3px; }
#menu .mname { font-size:12px; max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#menu .lv { flex:none; background:var(--sec); color:var(--muted); font-size:10px; padding:1px 6px;
            border-radius:2px; }
#menu .mgroup { padding:6px 14px 2px; font-size:10px; color:var(--muted); }
#menu .mrule { border-top:1px solid var(--line); margin:3px 0; }
#menu button.danger { color:var(--late-ink); }
"""

# JS は**生の文字列**（r"""）で持つ。ふつうの文字列にすると Python が `\n` を本物の改行に変えてしまい、
# JS の文字列リテラルが途中で切れて構文エラーになる（＝画面の機能が丸ごと死ぬ）。
# 折りたたみ（閲覧・編集の両方に付く）。行を DOM から消さずに隠すだけにして、印刷では CSS が必ず戻す
# ＝畳んだまま刷って白紙のフェーズを渡す事故が、そもそも起こらない形にする。
_VIEW_SCRIPT = r"""
(function(){
  // 時間軸の単位（月・週・日）。1 日あたりの幅を変えるだけ＝棒も格子も同じ表の中で伸び縮みするので、
  // 行と棒がずれない（表ごと横にスクロールする）。状態は必ずこの 3 つのどれかで、「自動」という状態は持たない
  // （自動は初期値の決め方であって、利用者が選ぶ状態ではない）。
  // 1 日あたりの幅（px）。月は狭く・日は広く＝粒度を落とすほどガントも短くなる。
  var PX={d:26,w:9,m:2.4};
  var COLS=__COLS__;
  var scroll=document.querySelector('.scroll');
  function unit(kind){
    if(!scroll) return;
    var days=Number(scroll.dataset.days||0);
    ['u-d','u-w','u-m'].forEach(function(c){ scroll.classList.remove(c); });
    scroll.classList.add('u-'+kind);
    // 単位ごとに幅を必ず入れる（月に切り替えたら短く、日で長く）。狭すぎて棒が読めないので下限を置く。
    if(days>0){ scroll.style.setProperty('--gw', Math.max(Math.round(days*PX[kind]),200)+'px'); }
    document.querySelectorAll('.zoom').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.dataset.zoom===kind)); });
    try{ sessionStorage.setItem('wbs-unit', kind); }catch(e){}
  }
  document.querySelectorAll('.zoom').forEach(function(b){
    b.addEventListener('click',function(){ unit(b.dataset.zoom); }); });
  // 列の表示・非表示。まとまりの見出しは残った列の数だけ幅を持つので、消したら数え直す。
  function recount(){
    var order=['work','plan','act'], counts={work:0,plan:0,act:0};
    var sizes=[COLS.work,COLS.plan,COLS.act], g=0, seen=0;
    document.querySelectorAll('thead tr:last-child th').forEach(function(c){
      if(seen>=sizes[g]){ g++; seen=0; }
      seen++;
      if(getComputedStyle(c).display!=='none') counts[order[g]]++;
    });
    order.forEach(function(k){
      var th=document.querySelector('.grp th[data-group="'+k+'"]');
      if(th) th.colSpan = Math.max(counts[k],1); });
  }
  document.querySelectorAll('.col').forEach(function(b){
    b.addEventListener('click',function(){
      var on=scroll.classList.toggle('hide-'+b.dataset.col);
      b.setAttribute('aria-pressed', String(!on));
      try{ sessionStorage.setItem('wbs-col-'+b.dataset.col, on?'off':'on'); }catch(e){}
      recount(); });
    var saved=null; try{ saved=sessionStorage.getItem('wbs-col-'+b.dataset.col); }catch(e){}
    if(saved==='off') scroll.classList.add('hide-'+b.dataset.col);
    b.setAttribute('aria-pressed', String(saved!=='off'));
  });
  recount();
  var saved=null; try{ saved=sessionStorage.getItem('wbs-unit'); }catch(e){}
  unit(saved || (scroll ? scroll.dataset.unit : 'w'));
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
_EDIT_SCRIPT = r"""
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
    } else if(td.dataset.choices){
      // 名簿から選ぶ欄。名簿に無い名前も入れられ、入れたら名簿にも足される。
      var list=JSON.parse(td.dataset.choices);
      if(old && list.indexOf(old)<0) list=[old].concat(list);
      box=document.createElement('select');
      var blank=document.createElement('option'); blank.value=''; blank.textContent='（なし）';
      box.appendChild(blank);
      list.forEach(function(v){
        var o=document.createElement('option'); o.value=v; o.textContent=v; box.appendChild(o); });
      var fresh=document.createElement('option'); fresh.value='\u0000new'; fresh.textContent='＋ 新しく入力…';
      box.appendChild(fresh);
      box.value=old;
    } else {
      box=document.createElement('input');
      box.type=(td.dataset.field==='start'||td.dataset.field==='due')?'date':'text';
      box.value=old;
    }
    td.textContent=''; td.appendChild(box); box.focus();
    var done=false;
    function commit(){
      if(done) return;
      if(box.value==='\u0000new') return;   // 新しく入力へ切り替える最中は保存しない
      done=true;
      if(box.value===old){ location.reload(); return; } send(td,box.value); }
    function cancel(){ if(done) return; done=true; location.reload(); }
    function swapToText(){
      var text=document.createElement('input'); text.type='text'; text.value='';
      td.textContent=''; td.appendChild(text); text.focus();
      box=text;
      text.addEventListener('blur',commit);
      text.addEventListener('keydown',function(e){
        if(e.key==='Enter'){ e.preventDefault(); commit(); } if(e.key==='Escape'){ cancel(); } });
    }
    box.addEventListener('blur',commit);
    box.addEventListener('change',function(){
      if(box.tagName!=='SELECT') return;
      if(box.value==='\u0000new'){ swapToText(); return; }
      commit();
    });
    box.addEventListener('keydown',function(e){
      if(e.key==='Enter'){ e.preventDefault(); commit(); } if(e.key==='Escape'){ cancel(); } });
  }
  function add(ref, where, milestone){
    if(busy) return; busy=true;
    fetch('add',{method:'POST',headers:{'Content-Type':'application/json','X-WBS-Token':token},
      body:JSON.stringify({ref:ref, where:where, milestone:!!milestone})})
      .then(function(r){ return r.json().then(function(b){ return {ok:r.ok,body:b}; }); })
      .then(function(r){ if(r.ok){ tell('足した: '+r.body.id); location.reload(); }
                         else { busy=false; tell(r.body.detail||'足せなかった',true); } })
      .catch(function(e){ busy=false; tell('足せなかった: '+e,true); });
  }
  function del(ref){
    if(busy) return; busy=true;
    fetch('remove',{method:'POST',headers:{'Content-Type':'application/json','X-WBS-Token':token},
      body:JSON.stringify({ref:ref})})
      .then(function(r){ return r.json().then(function(b){ return {ok:r.ok,body:b}; }); })
      .then(function(r){ if(r.ok){ tell('消した: '+ref); location.reload(); }
                         else { busy=false; tell(r.body.detail||'消せなかった',true); } })
      .catch(function(e){ busy=false; tell('消せなかった: '+e,true); });
  }
  var menu=document.getElementById('menu');
  function hideMenu(){
    if(menu) menu.style.display='none';
    document.querySelectorAll('tr.is-sel').forEach(function(r){ r.classList.remove('is-sel'); });
  }
  function item(label,fn){
    var b=document.createElement('button'); b.type='button'; b.textContent=label;
    b.addEventListener('click',function(){ hideMenu(); fn(); });
    return b;
  }
  function head(code,name,level){
    var h=document.createElement('div'); h.className='mhead';
    var t=document.createElement('span'); t.className='mname'; t.textContent=code+' '+name;
    var b=document.createElement('span'); b.className='lv'; b.textContent='Lv'+level;
    h.appendChild(t); h.appendChild(b); return h;
  }
  function group(text){
    var g=document.createElement('div'); g.className='mgroup'; g.textContent=text; return g;
  }
  function rule(){ var r=document.createElement('div'); r.className='mrule'; return r; }
  document.addEventListener('contextmenu',function(e){
    var tr=e.target.closest && e.target.closest('tr[data-ref]');
    if(!tr || !menu || !tr.dataset.ref) return;
    e.preventDefault();
    menu.textContent='';
    var ref=tr.dataset.ref, holder=tr.dataset.holder;
    var code=tr.dataset.code, name=tr.dataset.name||'', lv=Number(tr.dataset.level);
    menu.appendChild(head(code,name,lv));
    menu.appendChild(group('行を追加'));
    menu.appendChild(item('上に追加（同じ Lv'+lv+'）',function(){ add(ref,'above'); }));
    menu.appendChild(item('下に追加（同じ Lv'+lv+'）',function(){ add(ref,'below'); }));
    if(holder) menu.appendChild(item('子として追加（1 つ下の Lv'+(lv+1)+'）',function(){ add(ref,'child'); }));
    menu.appendChild(rule());
    menu.appendChild(item('マイルストーンを下に追加（◆）',function(){ add(ref,'below',true); }));
    menu.appendChild(rule());
    menu.appendChild(item('名前を変更',function(){
      var cell=tr.querySelector('td.edit.name'); if(cell) open(cell); }));
    menu.appendChild(rule());
    var kids=tr.dataset.kids==='1';
    var danger=item('この行を削除…',function(){
      var msg='「'+code+' '+name+'」（'+ref+'）を削除します。';
      if(kids) msg+='\n配下の行も一緒に削除されます。';
      if(window.confirm(msg+'\nよろしいですか？')) del(ref); });
    danger.className='danger';
    menu.appendChild(danger);
    hideMenu();
    tr.classList.add('is-sel');   // どの行を触っているかを画面でも示す
    menu.style.left=e.pageX+'px'; menu.style.top=e.pageY+'px'; menu.style.display='block';
  });
  document.addEventListener('click',hideMenu);
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') hideMenu(); });
  var addtop=document.getElementById('addtop');
  if(addtop) addtop.addEventListener('click',function(){ add(null,'top'); });
  document.addEventListener('click',function(e){
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
    data_span = wbs.span
    span = drawing_window(data_span) if data_span else None
    back = backdrop(span, wbs.today) if span else ""
    groups = "".join(
        f'<th class="grp-{key}{" gs" if key != "work" else ""}" data-group="{key}"'
        f' colspan="{sum(1 for _, _, g in COLUMNS if g == key)}">{_esc(label)}</th>'
        for key, label in COLUMN_GROUPS
    )
    axis = f'<th class="gantt" rowspan="2">{_axis_svg(span, wbs.today) if span else ""}</th>'
    head = "".join(f'<th class="{css}">{_esc(label)}</th>' for label, css, _ in COLUMNS)
    days = ((span[1] - span[0]).days + 1) if span else 0
    # 初期の単位は期間の長さで決める（短い案件は週・長い案件は月）。以後は利用者が選んだ単位が状態。
    unit = "m" if days > 120 else "w"
    rosters = {"teams": list(wbs.overlay.teams), "members": list(wbs.overlay.members)}
    parents = _holders(wbs.rows, "")
    body = _milestone_row(wbs, span) + "".join(
        _row_html(row, span, wbs.today, back, editable=editable, rosters=rosters, parent=parents.get(row.code, ""))
        for row in wbs.walk()
    )
    title = wbs.overlay.project or "WBS"
    client = f"<div>提出先: {_esc(wbs.overlay.client)}</div>" if wbs.overlay.client else ""
    period = f"　期間 {data_span[0].isoformat()} 〜 {data_span[1].isoformat()}" if data_span else ""
    banner = '<div class="meta" style="color:var(--late-ink)">下書き（未コミットの変更を含む）</div>' if draft else ""
    left = [
        '<button id="fold" type="button">すべて折りたたむ</button>',
        '<button id="unfold" type="button">すべて展開</button>',
        '<span class="sep">列</span>',
        '<button class="col" data-col="team" type="button">チーム</button>',
        '<button class="col" data-col="who" type="button">担当</button>',
    ]
    if editable:
        left.append('<button id="addtop" type="button">行を追加</button>')
    right = [
        '<span class="sep">時間軸</span>',
        '<button class="zoom" data-zoom="m" type="button">月</button>',
        '<button class="zoom" data-zoom="w" type="button">週</button>',
        '<button class="zoom" data-zoom="d" type="button">日</button>',
    ]
    ops = [f'<div class="left">{"".join(left)}</div>', f'<div class="right">{"".join(right)}</div>']
    edit_bits = ""
    if editable:
        banner += (
            '<div class="hint">セルをクリックすると直せる（Enter で保存・Esc で取り消し）。'
            "書き戻す先は正本（作業単位の frontmatter と docs/wbs.yaml）。導出される値に編集の口は無い。</div>"
        )
        edit_bits = (
            f'<div id="say"></div><div id="menu"></div><script data-token="{_esc(token)}">{_EDIT_SCRIPT}</script>'
        )
    inner = (
        f"<style>{_STYLE}{_EDIT_STYLE if editable else ''}</style>"
        f"<header><h1>{_esc(title)}</h1>{client}"
        f'<div class="meta">基準日 {wbs.today.isoformat()}{period}　{_esc(provenance)}</div>{banner}'
        f'<div class="ops">{"".join(ops)}</div></header>'
        f'<div class="scroll u-{unit}" data-days="{days}" data-unit="{unit}">'
        f'<table><thead><tr class="grp">{groups}{axis}</tr><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
        f"<footer>{_legend()}</footer><script>{_view_script()}</script>{edit_bits}"
    )
    return _DOCUMENT.format(title=_esc(title), body=inner)
