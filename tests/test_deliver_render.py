"""生成物（自己完結 HTML）と CLI のテスト。

提出物として成り立つ条件を機械で確かめる：外から何も読まないこと・すべての行が現れること・
遅れと未日程が印として出ること・空の工程表を黙って出さないこと。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from typer.testing import CliRunner

from harness.deliver import render
from harness.deliver import wbs as wbs_mod
from harness.deliver.cli import wbs_app
from harness.deliver.overlay import Overlay

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)

# 外部リソースを読む書き方（提出物に 1 つでもあれば、オフラインで開いたときに崩れる）。
_EXTERNAL = re.compile(r"https?://|<link\b|<script\b[^>]*\bsrc=|<img\b|url\(\s*['\"]?(?!data:)")


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """done 1 件・遅れ 1 件・節目 1 件・未日程 1 件がそろう最小の木。"""
    alpha = root / "work" / "EP-90-alpha"
    _write(alpha / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        alpha / "T-9001-a.md",
        {
            "id": "T-9001",
            "kind": "task",
            "status": "done",
            "title": "設計",
            "start": "2026-08-03",
            "due": "2026-08-07",
            "created": "2026-08-03",
            "closed": "2026-08-06",
        },
    )
    _write(
        alpha / "T-9002-b.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "todo",
            "title": "実装",
            "start": "2026-08-10",
            "due": "2026-08-12",  # 基準日 08-20 より前・未完＝遅れ
            "depends_on": ["T-9001"],
        },
    )
    _write(
        alpha / "T-9003-c.md",
        {"id": "T-9003", "kind": "task", "status": "todo", "title": "検収", "due": "2026-08-28", "milestone": True},
    )
    _write(root / "work" / "EP-92-gamma" / "item.md", {"id": "EP-92", "kind": "epic", "status": "todo"})


def _html(root: Path) -> str:
    built = wbs_mod.build(root, today=TODAY, overlay=Overlay())
    return render.render_html(built)


def test_every_row_appears_in_the_output(tmp_path: Path) -> None:
    """日程のある行も無い行も、すべて出力に現れる（黙って消える単位が無い）。"""
    _scaffold(tmp_path)
    html = _html(tmp_path)
    for item_id in ("EP-90", "T-9001", "T-9002", "T-9003", "EP-92"):
        assert item_id in html


def test_output_reads_nothing_from_outside(tmp_path: Path) -> None:
    """外部リソースへの参照が 1 つも無い（ファイル 1 つを転送すればそのまま開ける）。"""
    _scaffold(tmp_path)
    assert _EXTERNAL.search(_html(tmp_path)) is None


def test_late_row_is_marked_and_finished_one_is_not(tmp_path: Path) -> None:
    """遅れの印は予定終了を過ぎた未完の行だけに付く。"""
    _scaffold(tmp_path)
    rows = {row.ref: row for row in wbs_mod.build(tmp_path, today=TODAY, overlay=Overlay()).walk() if row.ref}
    html = _html(tmp_path)
    late_row = next(line for line in html.split("<tr") if "T-9002" in line)
    done_row = next(line for line in html.split("<tr") if "T-9001" in line)
    assert rows["T-9002"].late and "is-late" in late_row
    assert not rows["T-9001"].late and "is-late" not in done_row


def test_unscheduled_row_is_marked(tmp_path: Path) -> None:
    """日程の無い行はクラスで区別する（ガントが空なので見れば分かる。クライアント向けの一覧は出さない）。"""
    _scaffold(tmp_path)
    html = _html(tmp_path)
    unscheduled_row = next(line for line in html.split("<tr") if "EP-92" in line)
    assert "is-unscheduled" in unscheduled_row
    assert "未日程（" not in html  # 末尾の一覧は出さない


def test_milestone_is_drawn_as_a_point_not_a_bar(tmp_path: Path) -> None:
    """節目は期間を持たないので、棒でなく点（多角形）で描く。"""
    _scaffold(tmp_path)
    html = _html(tmp_path)
    milestone_row = next(line for line in html.split("<tr") if "T-9003" in line)
    assert '<span class="ms"' in milestone_row
    # 下敷き（非稼働日の帯）は全行に敷くので、無いことを見るのは**棒**だけ。
    assert not re.search(r'<rect class="(plan|done|late)"', milestone_row)


def test_today_line_is_drawn_inside_each_row(tmp_path: Path) -> None:
    """基準日の線は行ごとの図形の中に描く（表全体に重ねないので改ページでずれない）。"""
    _scaffold(tmp_path)
    html = _html(tmp_path)
    dated_row = next(line for line in html.split("<tr") if "T-9001" in line)
    assert 'class="today"' in dated_row


def test_export_writes_a_single_file(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    out = tmp_path / "out" / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()]
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "T-9001" in out.read_text(encoding="utf-8")


def test_export_refuses_when_nothing_is_scheduled(tmp_path: Path) -> None:
    """日程を持つ単位が 1 件も無ければ出力しない（空の工程表を黙って渡さない）。"""
    _write(tmp_path / "work" / "EP-93-delta" / "item.md", {"id": "EP-93", "kind": "epic", "status": "todo"})
    out = tmp_path / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()]
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_export_refuses_when_the_lint_fails(tmp_path: Path) -> None:
    """検査に失敗する状態では出力しない（間違った工程表を良い見た目で出さない）。"""
    _scaffold(tmp_path)
    _write(
        tmp_path / "work" / "EP-90-alpha" / "item.md",
        {
            "id": "EP-90",
            "kind": "epic",
            "status": "in-progress",
            "plan": "detailed",
            "start": "2026-08-01",  # 子を持つのに自分で日程を宣言している
            "due": "2026-08-31",
        },
    )
    out = tmp_path / "WBS.html"
    result = CliRunner().invoke(
        wbs_app, ["export", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()]
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_lint_command_reports_success_and_failure(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    runner = CliRunner()
    ok = runner.invoke(wbs_app, ["lint", "--root", str(tmp_path), "--today", TODAY.isoformat()])
    assert ok.exit_code == 0, ok.output
    _write(
        tmp_path / "work" / "EP-90-alpha" / "item.md",
        {
            "id": "EP-90",
            "kind": "epic",
            "status": "in-progress",
            "plan": "detailed",
            "start": "2026-08-01",
            "due": "2026-08-31",
        },
    )
    bad = runner.invoke(wbs_app, ["lint", "--root", str(tmp_path), "--today", TODAY.isoformat()])
    assert bad.exit_code == 1
