"""画面から行を消す（作業単位のファイル／手動行の記述を取り除く）。

消すのは正本だけ。作業単位はそのファイル（フォルダの単位ならフォルダごと）、手動行は上書きファイルの
その塊と、それを指している節の項目。**片方だけ消すと参照切れになる**ので、両方を 1 回の操作で取る。

配下を持つ単位は消さない（何が消えるのか画面から見えないまま、まとめて失うのを防ぐ）。先に配下を消す。
消した結果として検査に落ちる場合（他の単位が先行として指していた等）は、消したものを書き戻して理由を返す。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from harness import pm
from harness.deliver import history
from harness.deliver.editor import LOCK, EditRejected, find_item_path, row_bounds, walk_nodes
from harness.deliver.overlay import MANUAL_ID_PREFIX, OVERLAY_PATH
from harness.deliver.wbs_lint import all_problems


def _snapshot(paths: list[Path]) -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in paths if p.is_file()]


def _restore(saved: list[tuple[Path, str]]) -> None:
    for path, text in saved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _drop_manual_row(text: str, row_id: str) -> str:
    """上書きファイルから、その手動行の塊と、それを指している節の項目を取り除く。"""
    lines = text.splitlines()
    start, end, _ = row_bounds(lines, row_id)
    lines = lines[: start - 1] + lines[end:]  # `- id:` の行から塊の終わりまで
    pointer = re.compile(rf"^\s*-\s+row:\s*[\"']?{re.escape(row_id)}[\"']?\s*$")
    lines = [line for line in lines if not pointer.match(line)]
    return "\n".join(_drop_empty_keys(lines)) + "\n"


def _drop_empty_keys(lines: list[str]) -> list[str]:
    """項目が 1 つも残らなかった一覧のキー行を落とす。

    `rows:` だけが残ると値が空（None）になり、一覧として読めなくなる＝上書きファイルが壊れる。
    """
    empty = re.compile(r"^(\s*)(rows|entries):\s*$")
    out: list[str] = []
    for i, line in enumerate(lines):
        match = empty.match(line)
        if match is None:
            out.append(line)
            continue
        indent = len(match.group(1))
        following = next((later for later in lines[i + 1 :] if later.strip()), "")
        has_items = following.startswith(" " * (indent + 1)) and following.lstrip().startswith("-")
        if has_items:
            out.append(line)
    return out


def remove(root: Path, ref: str, *, today: date) -> None:
    """行を 1 つ消す。配下を持つ単位・消すと検査に落ちる場合は、理由を出して断る。"""
    with LOCK:
        before = {p.message for p in all_problems(root, today=today) if p.level == "error"}
        overlay_path = root / OVERLAY_PATH

        if ref.startswith(MANUAL_ID_PREFIX):
            if not overlay_path.is_file():
                raise EditRejected(f"手動行 '{ref}' が {OVERLAY_PATH} に見つからない")
            saved = _snapshot([overlay_path])
            history.record(overlay_path)  # 取り消しのため、変える直前の本文を記録
            overlay_path.write_text(_drop_manual_row(overlay_path.read_text(encoding="utf-8"), ref), encoding="utf-8")
        else:
            nodes, _ = pm.load_tree(root)
            node = next((n for n in walk_nodes(nodes) if n.item.id == ref), None)
            if node is None:
                raise EditRejected(f"作業単位 '{ref}' が work/ に見つからない")
            if node.children:
                raise EditRejected(
                    f"'{ref}' は配下に {len(node.children)} 件の単位を持っている。まとめて消さない"
                    f"（何が消えるか画面から見えないため）。先に配下を消す"
                )
            path = find_item_path(root, ref)
            targets = sorted(path.parent.rglob("*")) if path.name == pm.MARKER else [path]
            saved = _snapshot([p for p in targets if p.is_file()])
            for file in reversed([p for p in targets if p.is_file()]):
                history.record(file)  # 取り消しのため、消す前の本文を記録（復元でこの内容を書き戻す）
                file.unlink()
            if path.name == pm.MARKER:
                for directory in sorted((p for p in targets if p.is_dir()), reverse=True):
                    directory.rmdir()
                path.parent.rmdir()

        introduced = [p for p in all_problems(root, today=today) if p.level == "error" and p.message not in before]
        if introduced:
            _restore(saved)
            raise EditRejected("　/　".join(p.message for p in introduced))
