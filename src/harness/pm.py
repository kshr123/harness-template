"""プロジェクト管理の中核ロジック：作業単位の木の読み込み、進捗の算出、参照チェック。

- 作業単位＝意味のある 1 まとまり（ディレクトリ、または軽いときはファイル）。親は置き場所。
- 木を再帰的にたどって階層を作り、進捗は末端の単位の状態から算出する（手書きしない・二重に管理しない）。
- 親はフォルダなので参照エラーは起きない。代わりに ID の重複・depends_on の指す先が無い、を失敗にする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
from pydantic import ValidationError

from harness.models import Item, Kind, PlanMaturity, Status

WORK_DIR = "work"
REQUIREMENTS_DIR = "docs/requirements"
MARKER = "item.md"
# 軽い単位のファイル名の印。EP- / T- / INV- / E- で始まる .md を単位とみなす（notes.md 等の付属ファイルと区別する）。
UNIT_FILE = re.compile(r"^(EP|T|INV|E)-\d+.*\.md$")
_ARTIFACT_FILES = {MARKER, "STATUS.md", "SPEC.md", "PLAN.md", "notes.md", "README.md"}


@dataclass
class Node:
    """木の 1 ノード（作業単位）。children が空なら末端。"""

    item: Item
    path: Path
    children: list[Node] = field(default_factory=list)

    def leaves(self) -> list[Node]:
        """末端の単位（実際の作業）を集める。自分が末端ならば自分。"""
        if not self.children:
            return [self]
        out: list[Node] = []
        for c in self.children:
            out.extend(c.leaves())
        return out


@dataclass(frozen=True)
class Problem:
    """検証の指摘。level="error" だけが失敗（検証を止める）。"""

    level: str  # "error" | "info"
    message: str


def _parse_item(path: Path, problems: list[Problem]) -> Item | None:
    post = frontmatter.load(path)
    try:
        return Item.model_validate(dict(post.metadata))
    except ValidationError as exc:
        rel = path.name if path.name != MARKER else f"{path.parent.name}/{MARKER}"
        problems.append(Problem("error", f"{rel}: frontmatter が不正: {exc.error_count()} 件"))
        return None


def _load_dir(dir_path: Path, problems: list[Problem]) -> list[Node]:
    """ディレクトリ直下の作業単位（子ディレクトリの item.md と、印の付いたファイル）を読む。"""
    nodes: list[Node] = []
    for entry in sorted(dir_path.iterdir()):
        if entry.is_dir():
            marker = entry / MARKER
            if marker.is_file():
                item = _parse_item(marker, problems)
                if item is not None:
                    nodes.append(Node(item, entry, _load_dir(entry, problems)))
            # item.md の無いディレクトリ（code/ results/ configs/ 等）は付属物なので単位にしない。
        elif entry.suffix == ".md" and entry.name not in _ARTIFACT_FILES and UNIT_FILE.match(entry.name):
            item = _parse_item(entry, problems)
            if item is not None:
                nodes.append(Node(item, entry, []))
    return nodes


def load_tree(root: Path) -> tuple[list[Node], list[Problem]]:
    """work/ をたどって作業単位の木を作る。"""
    problems: list[Problem] = []
    work = root / WORK_DIR
    if not work.is_dir():
        return [], problems
    return _load_dir(work, problems), problems


def _all_nodes(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    for n in nodes:
        out.append(n)
        out.extend(_all_nodes(n.children))
    return out


def lint(root: Path) -> list[Problem]:
    """作業単位の検査。ID の重複・depends_on の指す先が無い・計画の詳しさの不整合を見る。"""
    top, problems = load_tree(root)
    everything = _all_nodes(top)

    # ID の重複＝失敗（一意・再利用しないため）。
    seen: dict[str, Path] = {}
    for n in everything:
        if n.item.id in seen:
            problems.append(Problem("error", f"{n.item.id}: ID が重複している（一意にすること）"))
        seen[n.item.id] = n.path

    # depends_on の指す先が無い＝参照エラー（失敗）。
    known = set(seen)
    for n in everything:
        for dep in n.item.depends_on:
            if dep not in known:
                problems.append(Problem("error", f"{n.item.id}: depends_on の '{dep}' が見つからない（参照エラー）"))

    # depends_on の循環（A→B→A）＝失敗。両端が実在すると上の参照チェックは通るため、DFS（白/灰/黒）で検出する。
    # 再帰でなく明示スタックの反復 DFS（深い依存鎖でも RecursionError で門番が落ちない）。
    graph = {n.item.id: [d for d in n.item.depends_on if d in known] for n in everything}
    color = dict.fromkeys(graph, 0)  # 0=白（未訪問）／1=灰（訪問中）／2=黒（確定）
    for start in graph:
        if color[start] != 0:
            continue
        path: list[str] = []
        dfs: list[tuple[str, int]] = [(start, 0)]  # (ノード, 次に見る子の添字)
        while dfs:
            node_id, idx = dfs[-1]
            if idx == 0:  # このノードの初回訪問時だけ灰にして経路へ積む
                color[node_id] = 1
                path.append(node_id)
            if idx < len(graph[node_id]):
                dfs[-1] = (node_id, idx + 1)
                dep = graph[node_id][idx]
                if color[dep] == 0:
                    dfs.append((dep, 0))
                elif color[dep] == 1:  # 灰へ戻る辺＝循環
                    cycle = [*path[path.index(dep) :], dep]
                    problems.append(Problem("error", f"{dep}: depends_on が循環している（{' → '.join(cycle)}）"))
            else:  # 子を見終えた＝確定（黒）にして経路から降ろす
                color[node_id] = 2
                path.pop()
                dfs.pop()

    # requirements の指す先が無い＝参照エラー（失敗）。depends_on の検査と対称にする。
    # docs/requirements/ が無い案件では要件の検査そのものを行わない（要件文書を持たない案件を咎めない）。
    req_dir = root / REQUIREMENTS_DIR
    if req_dir.is_dir():
        # ID は先頭の REQ-<番号>。ファイル名は REQ-001.md でも REQ-001-<短い説明>.md でもよい（単位の命名規則と対称）。
        known_reqs = {m.group() for p in req_dir.glob("REQ-*.md") if (m := re.match(r"REQ-\d+", p.stem))}
        referenced: set[str] = set()
        for n in everything:
            for req in n.item.requirements:
                referenced.add(req)
                if req not in known_reqs:
                    problems.append(
                        Problem("error", f"{n.item.id}: requirements の '{req}' が見つからない（参照エラー）")
                    )
        # どの単位からも参照されない要件＝未カバーの要件。計画中（未分解）は正常なので失敗にはしない。
        for req in sorted(known_reqs - referenced):
            problems.append(Problem("info", f"{req}: 未カバーの要件（どの単位からも参照されていない）"))

    # 完了↔検証の結びつけ：done のタスクは、対応するテスト（verified_by）を持ち、それが存在すること。
    # これにより「テストを書かずに done にする」自己申告完了を機械的に防ぐ。
    for n in everything:
        if n.item.kind is Kind.task and n.item.status is Status.done:
            if not n.item.verified_by:
                problems.append(Problem("error", f"{n.item.id}: done だが verified_by（対応するテスト）が無い"))
            for v in n.item.verified_by:
                parts = v.split("::")
                test_file = parts[0]
                target = root / test_file
                if not target.is_file():
                    problems.append(Problem("error", f"{n.item.id}: verified_by の '{test_file}' が見つからない"))
                    continue
                # ::名 が付いていれば、そのテスト名がファイル本文に在ることまで確かめる（穴埋め(b)）。
                # ファイルは在るが指すテストが無い「空振り」を防ぐ。名前だけの参照（::無し）は従来どおり許す。
                text = target.read_text(encoding="utf-8")
                for name in parts[1:]:
                    base = name.split("[")[0].strip()  # パラメータ化の [..] を落として素の名前で照合
                    # 単語境界で照合する（test_a が test_answer を含むファイルで空振りしないように）。
                    if base and not re.search(rf"\b{re.escape(base)}\b", text):
                        problems.append(
                            Problem("error", f"{n.item.id}: verified_by の '{name}' が {test_file} に見つからない")
                        )

    # 調査は done のとき、本文に「結論」の節が必須（verified_by の代わり。②自動検証）。
    for n in everything:
        if n.item.kind is Kind.investigation and n.item.status is Status.done:
            src = n.path if n.path.is_file() else n.path / MARKER
            if "## 結論" not in frontmatter.load(src).content:
                problems.append(Problem("error", f"{n.item.id}: done の調査に「## 結論」の節が無い"))

    # 実験は done のとき、結果記録（results/ の指標・設定・データ指紋）が必須（調査の「## 結論」検査と同型）。
    # 実験はフォルダ単位で再現一式を同居させる約束なので、ファイル単位の done は記録の置き場が無く失敗にする。
    for n in everything:
        if n.item.kind is Kind.experiment and n.item.status is Status.done:
            if n.path.is_file():
                problems.append(
                    Problem("error", f"{n.item.id}: done の実験はフォルダ単位で results/ に結果を同居させること")
                )
                continue
            results = n.path / "results"
            if not (results.is_dir() and any(results.iterdir())):
                problems.append(
                    Problem("error", f"{n.item.id}: done の実験に結果記録（results/ の指標・設定・データ指紋）が無い")
                )

    # plan=detailed なのに子の単位が無い＝分解し忘れの可能性（失敗にはしない）。
    for n in everything:
        if n.item.plan is PlanMaturity.detailed and n.item.kind is Kind.epic and not n.children:
            problems.append(Problem("info", f"{n.item.id}: plan=detailed だが子の単位が無い（分解し忘れの可能性）"))
        # outline で子が無い＝まだ分解していないだけ。何も言わない。

    return problems


def render_status(root: Path, extra_pending: list[str] | None = None) -> str:
    """作業単位の木から STATUS.md（自動生成のファイル）を算出する。手書き禁止。

    extra_pending は課題など、木の外から集約する「人の判断待ち」の行（呼び出し側が渡す）。
    """
    top, _ = load_tree(root)

    lines: list[str] = [
        "<!-- 自動生成：uv run status が作る。手で編集しないこと。 -->",
        "# STATUS（作業単位の進捗＋計画の詳しさ）",
        "",
        "| 単位 | 種類 | plan | done/総数 | blocked | 関連要件 |",
        "|---|---|---|---|---|---|",
    ]
    for node in top:
        _render_node(node, lines, depth=0)

    # 人の判断待ち（承認待ち・止まっている・未解決の質問）を集約する。
    # 人はここを見れば「要所が来た」と分かる（見に行かないと分からない状態を減らす）。
    pending: list[str] = []
    for n in _all_nodes(top):
        if n.item.status is Status.blocked:
            pending.append(f"- {n.item.display}：止まっている（blocked）")
        elif n.item.status is Status.in_review:
            pending.append(f"- {n.item.display}：承認待ち（in-review）")
    work = root / WORK_DIR
    if work.is_dir():
        for md in sorted(work.rglob("*.md")):
            if "[要確認]" in md.read_text(encoding="utf-8"):
                pending.append(f"- {md.relative_to(root)}：未解決の [要確認] あり")
    if extra_pending:
        pending.extend(extra_pending)

    lines.append("")
    lines.append("## 人の判断待ち")
    lines.extend(pending if pending else ["（なし）"])
    lines.append("")
    return "\n".join(lines)


def _render_node(node: Node, lines: list[str], depth: int) -> None:
    leaves = node.leaves()
    is_container = bool(node.children)
    total = len(leaves)
    done = sum(1 for lf in leaves if lf.item.status is Status.done)
    blocked = sum(1 for lf in leaves if lf.item.status is Status.blocked)

    if node.item.plan is PlanMaturity.outline and not is_container and node.item.kind is Kind.epic:
        progress = "—（未分解）"
    elif is_container:
        progress = f"{done}/{total}" + (" ✅" if total and done == total else "")
    else:
        progress = "1/1 ✅" if node.item.status is Status.done else f"0/1（{node.item.status.value}）"

    plan = node.item.plan.value if node.item.kind in (Kind.epic, Kind.experiment) else "—"
    reqs = ", ".join(node.item.requirements) if node.item.requirements else "—"
    indent = "　" * depth
    lines.append(f"| {indent}{node.item.display} | {node.item.kind.value} | {plan} | {progress} | {blocked} | {reqs} |")
    for child in node.children:
        _render_node(child, lines, depth + 1)


def spec_lint(root: Path) -> list[Problem]:
    """作業単位に SPEC.md があれば、必要な見出しがそろっているか確認する。

    SPEC は任意（無くてもよい）。ただし置いたら中身が欠けないようにする。
    """
    required = ["## 目的", "## 受け入れ基準", "## やらないこと", "## 最後の確認手順"]
    problems: list[Problem] = []
    for spec in sorted((root / WORK_DIR).rglob("SPEC.md")):
        text = spec.read_text(encoding="utf-8")
        missing = [h for h in required if h not in text]
        if missing:
            problems.append(Problem("error", f"{spec.parent.name}/SPEC.md: 必要な見出しが不足: {', '.join(missing)}"))
    return problems
