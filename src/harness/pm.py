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
MARKER = "item.md"
# 軽い単位のファイル名の印。EP- / T- / E- で始まる .md を単位とみなす（notes.md 等の付属ファイルと区別する）。
UNIT_FILE = re.compile(r"^(EP|T|E)-\d+.*\.md$")
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

    # plan=detailed なのに子の単位が無い＝分解し忘れの可能性（失敗にはしない）。
    for n in everything:
        if n.item.plan is PlanMaturity.detailed and n.item.kind is Kind.epic and not n.children:
            problems.append(Problem("info", f"{n.item.id}: plan=detailed だが子の単位が無い（分解し忘れの可能性）"))
        # outline で子が無い＝まだ分解していないだけ。何も言わない。

    return problems


def render_status(root: Path) -> str:
    """作業単位の木から STATUS.md（自動生成のファイル）を算出する。手書き禁止。"""
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

    plan = node.item.plan.value if node.item.kind is not Kind.task else "—"
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
