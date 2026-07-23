"""提出物の体裁（折りたたみ・由来の刻印・未コミットのときの拒否）のテスト。

いちばん怖いのは、畳んだまま印刷して白紙のフェーズをクライアントに渡すこと。行を DOM から消さずに
隠すだけにして、印刷では CSS が必ず戻す形にしてある＝その仕掛けが本当に入っているかを見る。
"""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from typer.testing import CliRunner

from harness.deliver import render, stamp
from harness.deliver import wbs as wbs_mod
from harness.deliver.cli import wbs_app
from harness.deliver.overlay import Overlay

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
GENERATED = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """親 1 件・子 2 件（折りたたみの対象が 1 つできる木）。"""
    alpha = root / "work" / "EP-90-alpha"
    _write(alpha / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        alpha / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "done", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        alpha / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-12"},
    )


def _built(root: Path) -> wbs_mod.Wbs:
    return wbs_mod.build(root, today=TODAY, overlay=Overlay())


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8")


def _repo(root: Path) -> None:
    """コミット済みの小さなリポジトリを作る（署名・フックは使わない）。"""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "初期", "--no-verify")


def test_a_parent_row_gets_a_toggle_and_children_are_addressable(tmp_path: Path) -> None:
    """親の行に折りたたみの取っ手が付き、子の行は WBS 番号で辿れる（隠す相手が決まる）。"""
    _scaffold(tmp_path)
    html = render.render_html(_built(tmp_path))
    assert '<button class="tw" type="button" data-code="1"' in html
    assert 'data-code="1.1"' in html
    assert 'data-code="1.2"' in html


def test_collapsed_rows_still_print(tmp_path: Path) -> None:
    """畳んだ行は隠れるだけで、印刷では必ず戻る（白紙のフェーズを渡す事故が起こらない）。"""
    _scaffold(tmp_path)
    html = render.render_html(_built(tmp_path))
    assert "tr.hid { display:none; }" in html
    assert "tr.hid { display:table-row !important; }" in html
    # 隠すのは表示だけ＝行そのものは常に本文に残っている（消してしまうと印刷でも戻せない）。
    for item_id in ("EP-90", "T-9001", "T-9002"):
        assert item_id in html


def test_the_fingerprint_follows_the_values_on_the_page(tmp_path: Path) -> None:
    """同じ値なら同じ指紋・値が変われば違う指紋（どの時点の計画かを後から照合できる）。"""
    _scaffold(tmp_path)
    first = stamp.tree_fingerprint(_built(tmp_path))
    assert stamp.tree_fingerprint(_built(tmp_path)) == first
    _write(
        tmp_path / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "start": "2026-08-10", "due": "2026-08-19"},
    )
    assert stamp.tree_fingerprint(_built(tmp_path)) != first


def test_the_stamp_names_the_commit_and_the_time(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _repo(tmp_path)
    line = stamp.stamp(tmp_path, _built(tmp_path), generated_at=GENERATED)
    assert stamp.commit_of(tmp_path) is not None
    assert str(stamp.commit_of(tmp_path)) in line
    assert "2026-08-20" in line
    assert stamp.tree_fingerprint(_built(tmp_path)) in line


def test_without_git_the_stamp_says_unknown_and_nothing_is_refused(tmp_path: Path) -> None:
    """git を前提にしない（リポジトリでない場所でも出せる）。"""
    _scaffold(tmp_path)
    assert stamp.commit_of(tmp_path) is None
    assert not stamp.is_dirty(tmp_path)
    assert "不明" in stamp.stamp(tmp_path, _built(tmp_path), generated_at=GENERATED)


def test_export_refuses_while_the_tree_is_dirty(tmp_path: Path) -> None:
    """未コミットの変更があるまま出すと、刻んだコミットが嘘になるので既定では出さない。"""
    _scaffold(tmp_path)
    _repo(tmp_path)
    (tmp_path / "work" / "EP-90-alpha" / "T-9002-b.md").write_text(
        "---\nid: T-9002\nkind: task\nstatus: todo\nstart: 2026-08-10\ndue: 2026-08-19\n---\n", encoding="utf-8"
    )
    assert stamp.is_dirty(tmp_path)
    out = tmp_path / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()]
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_draft_is_allowed_but_says_so_on_the_page(tmp_path: Path) -> None:
    """逃げ道は残すが、下書きだと見て分かる形にする（既定は拒否のまま）。"""
    _scaffold(tmp_path)
    _repo(tmp_path)
    (tmp_path / "work" / "EP-90-alpha" / "T-9002-b.md").write_text(
        "---\nid: T-9002\nkind: task\nstatus: todo\nstart: 2026-08-10\ndue: 2026-08-19\n---\n", encoding="utf-8"
    )
    out = tmp_path / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat(), "--draft"]
    )
    assert result.exit_code == 0, result.output
    assert "下書き" in out.read_text(encoding="utf-8")


def test_a_clean_tree_exports_with_its_provenance(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _repo(tmp_path)
    out = tmp_path / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()]
    )
    assert result.exit_code == 0, result.output
    page = out.read_text(encoding="utf-8")
    assert "コミット" in page
    assert stamp.tree_fingerprint(_built(tmp_path)) in page
    assert "下書き" not in page
