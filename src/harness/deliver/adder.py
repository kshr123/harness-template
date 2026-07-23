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
from harness.deliver import wbs_lint
from harness.deliver.editor import LOCK, EditRejected, find_item_path, walk_nodes

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


def add_child(root: Path, parent_ref: str | None, *, today: date) -> str:
    """`parent_ref` の下（None なら `work/` の直下）に作業単位を 1 つ作り、その ID を返す。

    親がまだ子を持っていなければ、親の日程・工数を新しい子へ移す（分解の意味に合わせる）。
    """
    with LOCK:
        return _add(root, parent_ref, today=today)


def _add(root: Path, parent_ref: str | None, *, today: date) -> str:
    nodes, problems = pm.load_tree(root)
    if any(p.level == "error" for p in problems):
        raise EditRejected("work/ の読み取りに失敗している状態では足せない（先に指摘を直す）")
    before = {p.message for p in wbs_lint.check(root, today=today) if p.level == "error"}
    new_id = _next_id(nodes)
    restore: tuple[Path, str] | None = None

    if parent_ref is None:
        directory = root / pm.WORK_DIR
        directory.mkdir(parents=True, exist_ok=True)
        inherited: dict[str, str] = {}
    else:
        parent_path = find_item_path(root, parent_ref)
        if parent_path.name != pm.MARKER:
            raise EditRejected(
                f"'{parent_ref}' はファイル 1 つの単位なので、この下には足せない"
                f"（下に置くならフォルダの単位にする＝分解の作業として行う）"
            )
        directory = parent_path.parent
        parent_text = parent_path.read_text(encoding="utf-8")
        has_children = any(node.children for node in walk_nodes(nodes) if node.item.id == parent_ref)
        inherited = {}
        if not has_children:
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
    introduced = [p for p in wbs_lint.check(root, today=today) if p.level == "error" and p.message not in before]
    if introduced:  # 足した結果として検査に落ちる状態を、正本に残さない
        target.unlink()
        if restore is not None:
            restore[0].write_text(restore[1], encoding="utf-8")
        raise EditRejected("　/　".join(p.message for p in introduced))
    return new_id
