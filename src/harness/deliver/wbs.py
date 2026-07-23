"""作業単位の木と案件固有の上書きを結合し、WBS の行を**導出**する（形式に依らない中核）。

出力形式（HTML・Excel）はここを呼ぶだけで、日程や進捗の計算を持たない＝計算が 1 か所にある。

導出の規則（保存しない値。`docs/wbs.yaml` にも frontmatter にも欄が無い）:

- **WBS 番号** … 木の位置から（節が 1、その子が 1.1、さらに子が 1.1.1）。行を挿し込めば振り直る＝番号は
  表示であって同一性ではない。行どうしの参照（先行タスク）は常に ID で書く。
- **営業日数** … 開始〜終了を暦（土日・祝日・案件の非稼働日）で数える。両端を含む。
- **親の日程** … 子の開始の最小・終了の最大（ロールアップ）。親自身が日程を宣言していても、子がいる限り
  子から導く（食い違いは `wbs_lint` が指摘する。矛盾を放置して両方を持たない）。
- **親の状態** … 子が全部 done なら done／止まっている子があれば blocked／動いた子があれば in-progress／
  それ以外は todo。
- **進捗** … 末端の done 数 ÷ 末端の総数（`uv run status` の進捗と同じ式＝2 つ目の式を作らない）。
- **実績** … 作業単位は `created`／`closed` から（親は子の最小・最大）。手動行は保存された実績日から。
- **遅れ** … 終了予定が基準日より前で、まだ done でないこと。可視化であって門番ではない。

日程を 1 件も持たない木からの生成は**失敗**にする（空のガントを黙って出さない＝空振りで緑にしない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from harness import pm
from harness.deliver.calendar import WorkCalendar
from harness.deliver.overlay import OVERLAY_PATH, ManualRow, Overlay, Section, load_overlay
from harness.models import Status

# 親の状態をどう畳むか。「動いている」とみなす子の状態（1 つでもあれば親は in-progress）。
_ACTIVE = frozenset({Status.in_progress, Status.in_review, Status.done})


@dataclass
class WbsRow:
    """WBS の 1 行（表示に必要なものが全部そろった状態）。保存されるのではなく毎回導出される。"""

    code: str  # WBS 番号（1.2.3）。木の位置から導く。
    name: str
    source: str  # "section"（顧客向けの節）| "work"（作業単位）| "manual"（手動行）
    ref: str | None  # 作業単位 ID または手動行 ID（節は None）
    # この行の値が保存されているファイル（節は None）。編集面が「どこへ書き戻すか」をここから引く
    # ＝書き戻し先を画面側で組み立て直さない（2 か所で同じ対応づけを持たない）。
    path: Path | None = None
    team: str | None = None
    assignees: list[str] = field(default_factory=list)
    milestone: bool = False
    start: date | None = None
    due: date | None = None
    effort_days: float | None = None
    status: Status | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    depends_on: list[str] = field(default_factory=list)
    workdays: int | None = None  # 営業日数（開始〜終了の両端を含む）
    done_leaves: int = 0
    total_leaves: int = 0
    late: bool = False
    children: list[WbsRow] = field(default_factory=list)

    @property
    def scheduled(self) -> bool:
        """日程（開始または終了）を持つか。持たない行は未日程として印を付けて出す（黙って消さない）。"""
        return self.start is not None or self.due is not None

    @property
    def progress(self) -> float:
        """末端の done 割合（0.0〜1.0）。末端が無ければ 0.0。"""
        return self.done_leaves / self.total_leaves if self.total_leaves else 0.0

    def walk(self) -> list[WbsRow]:
        """自分を含む配下の全行を、表示順（深さ優先）で返す。"""
        out = [self]
        for child in self.children:
            out.extend(child.walk())
        return out


def _rollup_status(children: list[WbsRow]) -> Status:
    """子の状態から親の状態を畳む。状態を持たない子（節）は無視する。"""
    states = [c.status for c in children if c.status is not None]
    if not states:
        return Status.todo
    if all(s is Status.done for s in states):
        return Status.done
    if any(s is Status.blocked for s in states):
        return Status.blocked
    if any(s in _ACTIVE for s in states):
        return Status.in_progress
    return Status.todo


def _min_date(values: list[date | None]) -> date | None:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def _max_date(values: list[date | None]) -> date | None:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _from_work(node: pm.Node, code: str, calendar: WorkCalendar, today: date) -> WbsRow:
    """作業単位（`work/` の 1 ノード）を WBS の行にする。子がいれば日程・状態・実績は子から導く。"""
    item = node.item
    children = [_from_work(child, f"{code}.{i}", calendar, today) for i, child in enumerate(node.children, start=1)]
    row = WbsRow(
        code=code,
        name=item.title or item.id,
        source="work",
        ref=item.id,
        path=node.path / pm.MARKER if node.path.is_dir() else node.path,
        team=None,  # 作業単位はチーム欄を持たない（顧客向けの区分は節の team で表す）
        assignees=[item.owner] if item.owner else [],
        milestone=item.milestone,
        effort_days=item.effort_days,
        depends_on=list(item.depends_on),
        children=children,
    )
    if children:
        # 親は子から導く。親自身が宣言した日程は使わない（食い違いは wbs_lint が指摘する）。
        row.start = _min_date([c.start for c in children])
        row.due = _max_date([c.due for c in children])
        row.status = _rollup_status(children)
        row.actual_start = _min_date([c.actual_start for c in children])
        finishes = [c.actual_finish for c in children]
        row.actual_finish = _max_date(finishes) if all(f is not None for f in finishes) else None
        row.done_leaves = sum(c.done_leaves for c in children)
        row.total_leaves = sum(c.total_leaves for c in children)
        row.effort_days = _sum_effort([c.effort_days for c in children]) or item.effort_days
    else:
        row.start = item.start
        row.due = item.due
        row.status = item.status
        row.actual_start = item.created
        row.actual_finish = item.closed if item.status is Status.done else None
        row.done_leaves = 1 if item.status is Status.done else 0
        row.total_leaves = 1
    _finish(row, calendar, today)
    return row


def _sum_effort(values: list[float | None]) -> float | None:
    """子の見積り工数の合計（1 つも無ければ None）。"""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _from_manual(manual: ManualRow, code: str, calendar: WorkCalendar, today: date, overlay_path: Path) -> WbsRow:
    """手動行（`work/` に置けない行）を WBS の行にする。状態・実績は保存された値をそのまま使う。"""
    row = WbsRow(
        code=code,
        name=manual.name,
        source="manual",
        ref=manual.id,
        path=overlay_path,
        team=manual.team,
        assignees=list(manual.assignees),
        milestone=manual.milestone,
        start=manual.start,
        due=manual.due,
        effort_days=manual.effort_days,
        status=manual.status,
        actual_start=manual.actual_start,
        actual_finish=manual.actual_finish,
        depends_on=list(manual.depends_on),
        done_leaves=1 if manual.status is Status.done else 0,
        total_leaves=1,
    )
    _finish(row, calendar, today)
    return row


def _finish(row: WbsRow, calendar: WorkCalendar, today: date) -> None:
    """行ごとに最後まで導出できる値（営業日数・遅れ）を埋める。"""
    if row.start is not None and row.due is not None:
        row.workdays = calendar.count(row.start, row.due)
    elif row.milestone and row.due is not None:
        row.workdays = 0  # 節目は期間ゼロ
    row.late = row.due is not None and row.due < today and row.status is not Status.done


def _section_row(section: Section, code: str, children: list[WbsRow], calendar: WorkCalendar, today: date) -> WbsRow:
    """顧客向けの節（フェーズ）の行。日程・状態・進捗はすべて中身から導く。"""
    row = WbsRow(
        code=code,
        name=section.name,
        source="section",
        ref=None,
        team=section.team,
        children=children,
        start=_min_date([c.start for c in children]),
        due=_max_date([c.due for c in children]),
        status=_rollup_status(children),
        actual_start=_min_date([c.actual_start for c in children]),
        done_leaves=sum(c.done_leaves for c in children),
        total_leaves=sum(c.total_leaves for c in children),
        effort_days=_sum_effort([c.effort_days for c in children]),
    )
    finishes = [c.actual_finish for c in children]
    row.actual_finish = _max_date(finishes) if finishes and all(f is not None for f in finishes) else None
    _finish(row, calendar, today)
    return row


def _index_nodes(nodes: list[pm.Node]) -> dict[str, pm.Node]:
    """作業単位 ID → ノードの索引（節の項目からの参照解決に使う）。"""
    index: dict[str, pm.Node] = {}
    for node in nodes:
        index[node.item.id] = node
        index.update(_index_nodes(node.children))
    return index


@dataclass
class Wbs:
    """導出し終えた WBS 一式（表示・検査の両方がこれを読む）。"""

    rows: list[WbsRow]  # 第 1 階層（節、または節を書かない案件では work/ 直下の単位）
    overlay: Overlay
    today: date
    problems: list[pm.Problem] = field(default_factory=list)

    def walk(self) -> list[WbsRow]:
        """全行を表示順で返す。"""
        out: list[WbsRow] = []
        for row in self.rows:
            out.extend(row.walk())
        return out

    @property
    def unscheduled(self) -> list[WbsRow]:
        """日程を持たない末端の行（黙って消さず、印を付けて出す対象）。"""
        return [r for r in self.walk() if not r.children and not r.scheduled]

    @property
    def span(self) -> tuple[date, date] | None:
        """日程を持つ行全体の期間（最小の開始〜最大の終了）。1 件も無ければ None。"""
        starts = [r.start for r in self.walk() if r.start is not None]
        dues = [r.due for r in self.walk() if r.due is not None]
        if not starts and not dues:
            return None
        first = min(starts) if starts else min(dues)
        last = max(dues) if dues else max(starts)
        return (first, last)


def build(root: Path, *, today: date, overlay: Overlay | None = None) -> Wbs:
    """`work/` の木と `docs/wbs.yaml` から WBS を導出する。

    `today` は明示引数（暗黙の「今日」を関数の中で読まない＝テストが基準日を決められる。乱数の種を
    明示引数で渡すのと同じ作法）。参照の解決に失敗した項目は `problems` に error として積む
    （`wbs_lint` と出力コマンドがこれを読んで止める＝検査と表示が同じ導出を見る）。
    """
    over = overlay if overlay is not None else load_overlay(root)
    calendar = over.calendar.to_calendar()
    nodes, problems = pm.load_tree(root)
    index = _index_nodes(nodes)
    manual_by_id = over.rows_by_id

    rows: list[WbsRow]
    if over.sections:
        rows = _build_sections(over, index, manual_by_id, calendar, today, problems, root / OVERLAY_PATH)
    else:
        # 節を書かない案件は、work/ 直下の単位がそのまま第 1 階層になる（設定ゼロで使える）。
        rows = [_from_work(node, str(i), calendar, today) for i, node in enumerate(nodes, start=1)]
    return Wbs(rows=rows, overlay=over, today=today, problems=problems)


def _build_sections(
    over: Overlay,
    index: dict[str, pm.Node],
    manual_by_id: dict[str, ManualRow],
    calendar: WorkCalendar,
    today: date,
    problems: list[pm.Problem],
    overlay_path: Path,
) -> list[WbsRow]:
    """節構成に従って第 1 階層を組む。参照が解決できない項目は落とさず error にする（fail-closed）。"""
    rows: list[WbsRow] = []
    for section_no, section in enumerate(over.sections, start=1):
        code = str(section_no)
        children: list[WbsRow] = []
        for entry_no, entry in enumerate(section.entries, start=1):
            child_code = f"{code}.{entry_no}"
            if entry.work is not None:
                node = index.get(entry.work)
                if node is None:
                    problems.append(
                        pm.Problem(
                            "error",
                            f"docs/wbs.yaml: 節 '{section.name}' が指す作業単位 '{entry.work}' が work/ に無い"
                            f"（消した単位を指したままにしない・wbs_lint）",
                        )
                    )
                    continue
                children.append(_from_work(node, child_code, calendar, today))
            elif entry.row is not None:  # SectionEntry の検証で work / row のどちらか一方であることは保証済み
                manual = manual_by_id.get(entry.row)
                if manual is None:
                    problems.append(
                        pm.Problem(
                            "error",
                            f"節 '{section.name}' が指す手動行 '{entry.row}' が rows: に無い（wbs_lint）",
                        )
                    )
                    continue
                children.append(_from_manual(manual, child_code, calendar, today, overlay_path))
        rows.append(_section_row(section, code, children, calendar, today))
    return rows
