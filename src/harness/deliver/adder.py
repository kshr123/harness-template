"""画面から作業単位を足す（`work/` に新しいファイルを作る）。

WBS を見ながら「ここに 1 本足したい」は普通に起きるので、編集面から足せるようにする。ただし足すのは
**作業単位の正本**（`work/` のファイル）で、WBS 側には何も持たない＝ここでも台帳は 1 つのまま。

置き場は「親はフォルダ」の原則どおり：フォルダの単位（`item.md` を持つディレクトリ）の下にファイルを 1 つ作る。
ファイル 1 つで表されている軽い単位の下には置けない（そこに子を置くならフォルダにする必要があり、それは
画面の操作でなく分解の作業＝人が決めること）。

**分解した親から日程を移す**：子のいない単位は自分の日程を持てるが、子ができた瞬間、親の日程は子から導く値に
なる（宣言が残っていると検査に失敗する）。そこで最初の子を足すときに、親の日程・工数をその子へ移す。
「未分解のフェーズを分解する」がそのまま 1 操作になり、不変条件も保たれる。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from harness import pm
from harness.deliver.editor import LOCK, EditRejected, find_item_path, walk_nodes
from harness.deliver.wbs_lint import all_problems

# 足す単位の ID の形（作業単位の既定）。番号は既存の最大＋1 で、再利用しない。
_ID_PREFIX = "T-"
_ID_DIGITS = 4

# 親から子へ移す欄（親に残すと「子を持つのに日程を宣言している」検査に失敗する）。
_MOVED_TO_CHILD = ("start", "due", "effort_days")

_NEW_TITLE = "新しい作業"


def _next_id(nodes: list[pm.Node]) -> str:
    """まだ使っていない作業単位の ID（既存の最大の番号＋1）。"""
    used = [int(m.group(1)) for node in walk_nodes(nodes) if (m := re.fullmatch(r"T-(\d+)", node.item.id))]
    return f"{_ID_PREFIX}{max(used, default=0) + 1:0{_ID_DIGITS}d}"


def _frontmatter_value(text: str, key: str) -> str | None:
    """frontmatter からその欄の 1 行を取り出す（無ければ None）。"""
    match = re.search(rf"(?m)^{re.escape(key)}\s*:(.*)$", text)
    return match.group(1).strip() if match else None


def _strip_keys(text: str, keys: tuple[str, ...]) -> str:
    """frontmatter からその欄の行を落とす。"""
    for key in keys:
        text = re.sub(rf"(?m)^{re.escape(key)}\s*:.*$\n?", "", text)
    return text


# 並び順の刻み。間に挿せるよう、詰めずに間隔を空けて振る。
_ORDER_STEP = 10


def add_child(root: Path, parent_ref: str | None, *, today: date) -> str:
    """`parent_ref` の下（None なら `work/` の直下）に作業単位を 1 つ作り、その ID を返す。

    親がまだ子を持っていなければ、親の日程・工数を新しい子へ移す（分解の意味に合わせる）。
    """
    with LOCK:
        return _add(root, parent_ref, today=today)


def add_sibling(root: Path, ref: str, *, above: bool, today: date) -> str:
    """`ref` の**すぐ上／すぐ下**に、同じ置き場の作業単位を 1 つ作る。

    並びはファイル名の順（実質 ID 順）で、ID は既存の最大＋1 でしか採れない。だから「上に足す」は
    順序を書かないと表現できない。ここで**その置き場の並び順をいったん書き出し**（今の見た目のまま
    10 刻みで振る）、新しい行にはその間の値を与える。以後の挿入は 1 行の書き足しで済む。
    """
    with LOCK:
        nodes, _ = pm.load_tree(root)
        target = next((n for n in walk_nodes(nodes) if n.item.id == ref), None)
        if target is None:
            raise EditRejected(f"作業単位 '{ref}' が work/ に見つからない")
        siblings = _siblings_of(nodes, ref)
        holder = _holder_of(root, nodes, ref)
        new_id = _add(root, holder, today=today, skip_inherit=True)
        _renumber(siblings, ref, new_id, above=above, root=root)
        return new_id


def _siblings_of(nodes: list[pm.Node], ref: str) -> list[pm.Node]:
    """その単位と同じ置き場に並んでいる単位（自分を含む・表示順）。"""
    if any(n.item.id == ref for n in nodes):
        return nodes
    for node in nodes:
        found = _siblings_of(node.children, ref)
        if found:
            return found
    return []


def _holder_of(root: Path, nodes: list[pm.Node], ref: str) -> str | None:
    """その単位が入っている置き場（フォルダの単位の ID。`work/` 直下なら None）。"""
    for node in nodes:
        if any(child.item.id == ref for child in node.children):
            return node.item.id
        found = _holder_of(root, node.children, ref)
        if found is not None:
            return found
    return None


def _renumber(siblings: list[pm.Node], ref: str, new_id: str, *, above: bool, root: Path) -> None:
    """その置き場の並び順を書き出し直す（今の見た目のまま 10 刻み・新しい行を狙った位置へ）。"""
    order = [n.item.id for n in siblings]
    at = order.index(ref)
    order.insert(at if above else at + 1, new_id)
    nodes, _ = pm.load_tree(root)
    by_id = {n.item.id: n for n in walk_nodes(nodes)}
    for position, item_id in enumerate(order, start=1):
        node = by_id.get(item_id)
        if node is None:
            continue
        path = node.path / pm.MARKER if node.path.is_dir() else node.path
        text = path.read_text(encoding="utf-8")
        value = position * _ORDER_STEP
        new_text, count = re.subn(r"(?m)^order\s*:.*$", f"order: {value}", text, count=1)
        if count == 0:
            new_text = text.replace("\nid:", f"\norder: {value}\nid:", 1)
        path.write_text(new_text, encoding="utf-8")


def _add(root: Path, parent_ref: str | None, *, today: date, skip_inherit: bool = False) -> str:
    nodes, problems = pm.load_tree(root)
    if any(p.level == "error" for p in problems):
        raise EditRejected("work/ の読み取りに失敗している状態では足せない（先に指摘を直す）")
    before = {p.message for p in all_problems(root, today=today) if p.level == "error"}
    new_id = _next_id(nodes)
    restore: tuple[Path, str] | None = None
    moved: tuple[Path, Path] | None = None  # 分解でファイルをフォルダへ移したときの元と先

    if parent_ref is None:
        directory = root / pm.WORK_DIR
        directory.mkdir(parents=True, exist_ok=True)
        inherited: dict[str, str] = {}
    else:
        parent_path = find_item_path(root, parent_ref)
        if parent_path.name != pm.MARKER:
            # ファイル 1 つで表していた単位に子を足す＝**分解する**。親はフォルダで表す決まりなので、
            # そのファイルを同名のフォルダの `item.md` へ移し、下に置けるようにする。
            folder = parent_path.parent / parent_path.stem
            if folder.exists():
                raise EditRejected(f"'{parent_ref}' を分解しようとしたが {folder.name} が既にある")
            folder.mkdir()
            parent_path.rename(folder / pm.MARKER)
            moved = (parent_path, folder / pm.MARKER)
            parent_path = folder / pm.MARKER
        directory = parent_path.parent
        parent_text = parent_path.read_text(encoding="utf-8")
        has_children = any(node.children for node in walk_nodes(nodes) if node.item.id == parent_ref)
        inherited = {}
        if not has_children and not skip_inherit:
            for key in _MOVED_TO_CHILD:
                value = _frontmatter_value(parent_text, key)
                if value:
                    inherited[key] = value
            if inherited:
                restore = (parent_path, parent_text)
                parent_path.write_text(_strip_keys(parent_text, _MOVED_TO_CHILD), encoding="utf-8")

    target = directory / f"{new_id}-新しい作業.md"
    lines = [
        "---",
        f"id: {new_id}",
        "kind: task",
        "status: todo",
        f"title: {_NEW_TITLE}",
        f"created: {today.isoformat()}",
        *[f"{key}: {value}" for key, value in inherited.items()],
        "requirements: []",
        "depends_on: []",
        "verified_by: []",
        "---",
        f"# {new_id} {_NEW_TITLE}",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    introduced = [p for p in all_problems(root, today=today) if p.level == "error" and p.message not in before]
    if introduced:  # 足した結果として検査に落ちる状態を、正本に残さない
        target.unlink()
        if restore is not None:
            restore[0].write_text(restore[1], encoding="utf-8")
        if moved is not None:  # 分解も元に戻す（フォルダへ移したファイルをファイルへ戻す）
            moved[1].rename(moved[0])
            moved[1].parent.rmdir()
        raise EditRejected("　/　".join(p.message for p in introduced))
    return new_id
