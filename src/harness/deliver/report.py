"""定例・最終報告の 1 枚（自己完結 HTML）。ガントでなく「報告」＝印刷して渡す前提。

**新しい台帳を作らない**：ここに出る値はすべて既存の導出（`wbs.build` の木・`baseline.changes_since` の差・
`stamp` の刻印）を組み合わせるだけ。日付・状態・遅れ・マイルストーンの達成は `work/` の正本から導く。
色は `render` の色トークン 1 か所を参照する（色の第 2 台帳を作らない）。レイアウトだけ報告固有。

構成（0 件の節も「該当なし／遅れなし」と明記する＝黙って消さない）：
1. 前回からの変化（`--against` を渡したときだけ）
2. マイルストーンの状況（達成／遅れ／予定）。**達成は実績日で示し、期日を過ぎた達成は予定と実績の両方**を出す
   （done かどうかだけで分けると、期日超過の達成が「達成」に化けて粉飾になる）。
3. 遅れている作業
4. 今後 N 日の予定
5. 付録：要件トレース（T-0283 で足す。要件層が無ければ節ごと出さない）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from harness.deliver.render import _DOCUMENT, _TOKENS, _esc
from harness.models import Status

if TYPE_CHECKING:
    from harness.deliver.baseline import Change
    from harness.deliver.wbs import Wbs, WbsRow

_REPORT_STYLE = (
    _TOKENS
    + """
* { box-sizing:border-box; }
body { margin:0; padding:20px 24px; color:var(--ink); background:var(--paper);
       font:13px/1.5 "Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif; }
header { border-bottom:2px solid var(--ink); padding-bottom:8px; margin-bottom:16px; }
h1 { font-size:16px; font-weight:700; margin:0 0 2px; }
.meta { color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }
section { margin:0 0 18px; }
h2 { font-size:13px; font-weight:700; margin:0 0 6px; padding-bottom:3px; border-bottom:1px solid var(--line-strong); }
.none { color:var(--muted); font-size:12px; }
ul.items { list-style:none; margin:0; padding:0; }
ul.items li { padding:3px 0; border-bottom:1px solid var(--line); font-size:12px;
              display:flex; gap:10px; align-items:baseline; }
.who { color:var(--muted); font-size:11px; }
.when { font-variant-numeric:tabular-nums; color:var(--muted); font-size:11px; white-space:nowrap; }
.badge { flex:none; font-size:10px; font-weight:700; padding:0 6px; border-radius:3px; }
.b-done { background:var(--sec); color:var(--muted); }
.b-late { background:var(--late-row); color:var(--late-ink); }
.b-plan { background:var(--sec); color:var(--ink); }
.late { color:var(--late-ink); }
.ms { color:var(--bar-done); }
@media print { body { padding:0; } a { color:inherit; } }
"""
)


def _fmt(day: date | None) -> str:
    return day.isoformat() if day is not None else "（未定）"


def _who(row: WbsRow) -> str:
    """チーム / 担当（両方あれば「/」で繋ぐ）。利用者由来なのでエスケープする。"""
    sep = " / " if row.team and row.assignees else ""
    text = f"{row.team or ''}{sep}{'、'.join(row.assignees)}"
    return f'<span class="who">{_esc(text)}</span>'


def _leaves(wbs: Wbs) -> list[WbsRow]:
    """末端行（子を持たない＝実際の作業。親は集約なので報告の明細には出さない）。"""
    return [row for row in wbs.walk() if not row.children]


def _milestones_section(wbs: Wbs, today: date) -> str:
    """マイルストーンの状況。達成は実績日で示し、期日超過の達成は予定と実績の両方を出す（粉飾しない）。"""
    marks = [r for r in wbs.walk() if r.milestone and r.due is not None]
    if not marks:
        return _section("マイルストーンの状況", '<p class="none">マイルストーンなし</p>')
    items: list[str] = []
    for row in sorted(marks, key=lambda r: (r.due or date.max, r.name)):
        name = f'<span class="ms">◆</span> {_esc(row.name)}'
        if row.status is Status.done:
            done_day = row.actual_finish
            if done_day is not None and row.due is not None and done_day > row.due:
                # 期日を過ぎてからの達成＝予定と実績の両方を出す（「達成」で塗り潰さない）。
                when = f"予定 {_fmt(row.due)} → 実績 {_fmt(done_day)}"
                items.append(_item(name, '<span class="badge b-late">遅れて達成</span>', when))
            else:
                items.append(_item(name, '<span class="badge b-done">達成</span>', f"実績 {_fmt(done_day or row.due)}"))
        elif row.late:
            days = (today - row.due).days if row.due is not None else 0
            items.append(
                _item(name, '<span class="badge b-late">遅れ</span>', f"予定 {_fmt(row.due)}（{days} 日超過）")
            )
        else:
            items.append(_item(name, '<span class="badge b-plan">予定</span>', f"予定 {_fmt(row.due)}"))
    return _section("マイルストーンの状況", f'<ul class="items">{"".join(items)}</ul>')


def _late_section(wbs: Wbs, today: date) -> str:
    """遅れている作業（末端・マイルストーン以外）。0 件なら「遅れなし」と明記する。"""
    rows = [r for r in _leaves(wbs) if r.late and not r.milestone]
    if not rows:
        return _section("遅れている作業", '<p class="none">遅れなし</p>')
    items = []
    for row in sorted(rows, key=lambda r: (r.due or date.max, r.name)):
        days = (today - row.due).days if row.due is not None else 0
        when = f'<span class="when late">予定終了 {_fmt(row.due)}（{days} 日超過）</span>'
        items.append(f"<li><span>{_esc(row.name)}</span>{_who(row)}<span style='flex:1'></span>{when}</li>")
    return _section("遅れている作業", f'<ul class="items">{"".join(items)}</ul>')


def _upcoming_section(wbs: Wbs, today: date, horizon_days: int) -> str:
    """今後 N 日の予定（末端・未完で、窓に掛かる作業）。0 件なら「該当なし」と明記する。"""
    horizon = today + timedelta(days=horizon_days)
    rows = [
        r
        for r in _leaves(wbs)
        if not r.milestone
        and r.status is not Status.done
        and r.start is not None
        and r.due is not None
        and r.start <= horizon
        and r.due >= today
    ]
    if not rows:
        return _section(f"今後 {horizon_days} 日の予定", '<p class="none">該当なし</p>')
    items = []
    for row in sorted(rows, key=lambda r: (r.start or date.max, r.name)):
        when = f'<span class="when">{_fmt(row.start)} 〜 {_fmt(row.due)}</span>'
        items.append(f"<li><span>{_esc(row.name)}</span>{_who(row)}<span style='flex:1'></span>{when}</li>")
    return _section(f"今後 {horizon_days} 日の予定", f'<ul class="items">{"".join(items)}</ul>')


def _changes_section(changes: list[Change]) -> str:
    """前回からの変化（`--against` 指定時のみ）。理由は baseline が添えるコミット件名をそのまま使う。"""
    if not changes:
        return _section("前回からの変化", '<p class="none">計画は動いていない</p>')
    items = "".join(f"<li><span>{_esc(change.line())}</span></li>" for change in changes)
    return _section("前回からの変化", f'<ul class="items">{items}</ul>')


def _item(name: str, badge: str, when: str) -> str:
    return f"<li>{badge}<span>{name}</span><span style='flex:1'></span><span class='when'>{_esc(when)}</span></li>"


def _section(title: str, body: str) -> str:
    return f"<section><h2>{_esc(title)}</h2>{body}</section>"


def render_report(
    wbs: Wbs,
    *,
    today: date,
    provenance: str = "",
    draft: bool = False,
    against: str | None = None,
    changes: list[Change] | None = None,
    horizon_days: int = 14,
) -> str:
    """定例・最終報告の 1 枚を組む。値はすべて既存の導出の合成（新しい保存を作らない）。"""
    title = wbs.overlay.project or "WBS"
    banner = '<div class="meta" style="color:var(--late-ink)">下書き（未コミットの変更を含む）</div>' if draft else ""
    agreed = f"　合意した時点: {_esc(against)}" if against else ""
    parts: list[str] = []
    if against is not None:
        parts.append(_changes_section(changes or []))
    parts.append(_milestones_section(wbs, today))
    parts.append(_late_section(wbs, today))
    parts.append(_upcoming_section(wbs, today, horizon_days))
    body = (
        f"<style>{_REPORT_STYLE}</style>"
        f"<header><h1>{_esc(title)}　報告</h1>"
        f'<div class="meta">本日 {today.isoformat()}{agreed}　{_esc(provenance)}</div>{banner}</header>'
        f"{''.join(parts)}"
    )
    return _DOCUMENT.format(title=_esc(title), body=body)
