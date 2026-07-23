"""WBS の不変条件の検査（deliver プロファイルの検査）。

検査と表示は**同じ導出**（`wbs.build`）を読む＝「画面には出ているが検査は見ていない」経路を作らない。

ここで止めるもの:

- 節構成が指す作業単位・手動行が実在しない（消した単位を指したまま＝黙って行が減る）。
- 定義した手動行がどの節からも参照されていない（書いたのに出ない＝黙って消える）。
- 顧客向けの節構成が `work/` の単位を覆っていない（載せない単位は `exclude` に明示する＝差分に残す）。
- 同じ作業単位を 2 か所の節が指している（進捗が二重に数えられる）。
- 子を持つ単位が自分で日程を宣言している（親の日程は子から導くので、宣言した値は必ずどこかで嘘になる）。
- 先行する単位の終了予定より、後続の開始予定が前にある（依存と日程の矛盾）。

上書きファイルが無い案件では、節構成が空＝木をそのまま出すので、覆いの検査は何も要求しない。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from harness import pm
from harness.deliver import wbs as wbs_mod
from harness.deliver.overlay import Overlay


def _covered_ids(over: Overlay) -> set[str]:
    """節構成が直接指している作業単位の ID（配下は木をたどって覆われたとみなす）。"""
    return {e.work for s in over.sections for e in s.entries if e.work is not None}


def _referenced_rows(over: Overlay) -> set[str]:
    """節構成が指している手動行の ID。"""
    return {e.row for s in over.sections for e in s.entries if e.row is not None}


def _uncovered(nodes: list[pm.Node], covered: set[str], excluded: set[str]) -> list[str]:
    """節構成にも `exclude` にも入っていない作業単位を、上から順に探す（覆われた枝の中は見ない）。"""
    missing: list[str] = []
    for node in nodes:
        if node.item.id in covered or node.item.id in excluded:
            continue
        if node.children:
            missing.extend(_uncovered(node.children, covered, excluded))
            if not any(c.item.id in covered or c.item.id in excluded for c in node.children):
                missing.append(node.item.id)
        else:
            missing.append(node.item.id)
    return sorted(set(missing))


def _descendants(node: pm.Node) -> set[str]:
    """その単位と、その配下すべての ID（節が指した範囲＝実際に出る行の集合）。"""
    out = {node.item.id}
    for child in node.children:
        out |= _descendants(child)
    return out


def _find(nodes: list[pm.Node], item_id: str) -> pm.Node | None:
    for node in nodes:
        if node.item.id == item_id:
            return node
        found = _find(node.children, item_id)
        if found is not None:
            return found
    return None


def _overlapping_sections(over: Overlay, nodes: list[pm.Node]) -> list[pm.Problem]:
    """2 つの節が同じ作業単位を出してしまう組み合わせを集める。

    ID の完全一致だけを見ると、「節 A がエピックを、節 B がその中のタスクを指す」形を見逃す（実際に
    起こりやすい：エピックごと載せた後、目玉のタスクだけ別のフェーズにも出す）。この形では同じ作業が
    2 行として出て、進捗の末端も二重に数えられる。**指した範囲どうしの重なり**で見る。
    """
    problems: list[pm.Problem] = []
    claimed: dict[str, str] = {}  # 出る行の ID → それを出している節の名前
    reported: set[tuple[str, str]] = set()  # 報告済みの節の組（配下の分まで並べない）
    for section in over.sections:
        for entry in section.entries:
            if entry.work is None:
                continue
            node = _find(nodes, entry.work)
            if node is None:
                continue  # 参照切れは build 側が error にする
            for item_id in sorted(_descendants(node)):
                owner = claimed.get(item_id)
                if owner is None:
                    claimed[item_id] = section.name
                    continue
                # 重なりは配下にも連鎖するので、節の組ごとに 1 件だけ（先頭の単位）を報告する。
                pair = (owner, section.name)
                if pair in reported:
                    continue
                reported.add(pair)
                problems.append(
                    pm.Problem(
                        "error",
                        f"作業単位 '{item_id}' が節 '{owner}' と節 '{section.name}' の両方に出る"
                        f"（同じ作業が 2 行になり、進捗が二重に数えられる・wbs_lint）",
                    )
                )
    return problems


def _parent_declared_dates(nodes: list[pm.Node]) -> list[str]:
    """子を持つのに自分で日程を宣言している単位の ID（親の日程は子から導くので二重になる）。"""
    found: list[str] = []
    for node in nodes:
        if node.children:
            if node.item.start is not None or node.item.due is not None:
                found.append(node.item.id)
            found.extend(_parent_declared_dates(node.children))
    return found


def check(root: Path, *, today: date, overlay: Overlay | None = None) -> list[pm.Problem]:
    """WBS の不変条件を検査する（基準日を明示引数で受ける＝呼ぶ側が決める）。"""
    built = wbs_mod.build(root, today=today, overlay=overlay)
    problems = list(built.problems)
    over = built.overlay
    nodes, _ = pm.load_tree(root)

    if over.sections:
        covered = _covered_ids(over)
        excluded = set(over.exclude)
        for item_id in _uncovered(nodes, covered, excluded):
            problems.append(
                pm.Problem(
                    "error",
                    f"作業単位 '{item_id}' が docs/wbs.yaml のどの節にも載っていない。顧客向けの WBS から"
                    f"意図して外すなら exclude に書く（黙って消えるのを止める・wbs_lint）",
                )
            )
        problems.extend(_overlapping_sections(over, nodes))

    # 手動行の参照検査は節の有無に関わらず回す。節を書かない案件で rows: を書くと、どこにも出ないまま
    # 検査も通ってしまう（書いたのに出ない＝黙って消える形）。手動行は節からしか置けないので、
    # 節が無いのに手動行がある状態そのものが誤り。
    referenced = _referenced_rows(over)
    for row in over.rows:
        if row.id not in referenced:
            hint = "節（sections）を書いて、その entries に row として並べる" if not over.sections else "節から参照する"
            problems.append(
                pm.Problem(
                    "error",
                    f"手動行 '{row.id}' をどの節も参照していない（書いたのに出ない行を作らない）。{hint}（wbs_lint）",
                )
            )

    for item_id in _parent_declared_dates(nodes):
        problems.append(
            pm.Problem(
                "error",
                f"'{item_id}' は子を持つのに自分で start/due を宣言している。親の日程は子から導くので、"
                f"宣言した値はいつか子と食い違う。子に日程を置き、親からは外す（wbs_lint）",
            )
        )

    problems.extend(_dependency_order(built))
    return problems


def _dependency_order(built: wbs_mod.Wbs) -> list[pm.Problem]:
    """先行する単位の終了予定より後続の開始予定が前にある矛盾を集める。"""
    by_id = {row.ref: row for row in built.walk() if row.ref is not None}
    problems: list[pm.Problem] = []
    for row in built.walk():
        if row.start is None:
            continue
        for dep_id in row.depends_on:
            dep = by_id.get(dep_id)
            if dep is None or dep.due is None:
                continue
            if row.start < dep.due:
                problems.append(
                    pm.Problem(
                        "error",
                        f"'{row.ref}' は '{dep_id}' の後に来るのに、開始予定 {row.start} が "
                        f"'{dep_id}' の終了予定 {dep.due} より前にある（wbs_lint）",
                    )
                )
    return problems


def run_checks(root: Path) -> list[pm.Problem]:
    """verify から呼ばれる入口。基準日は実行日（この検査の合否は基準日に依らない）。"""
    return check(root, today=date.today())


def all_problems(root: Path, *, today: date) -> list[pm.Problem]:
    """書き換えの前後で見る指摘の全部（作業単位の検査＋WBS の検査）。

    WBS の検査だけを見ると、参照が切れた `depends_on` のような**作業単位の側の**壊れ方を通してしまう
    （画面から消した単位を他が指したまま、になる）。書き込む口は必ずこちらを見る。
    """
    return pm.lint(root) + check(root, today=today)
