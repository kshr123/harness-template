"""定例・最終報告の 1 枚（`wbs report` / report.render_report）のテスト。

報告に出る値はすべて木・baseline・stamp の導出の合成。ここでは「達成/遅れ/予定の区分」「期日超過の達成を
粉飾しない」「0 件の節を明記する」「拒否は export と同じ」「利用者文字列のエスケープ」をテストデータから確かめる。
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from typer.testing import CliRunner

from harness.deliver import report as report_mod
from harness.deliver import wbs as wbs_mod
from harness.deliver.cli import wbs_app
from harness.deliver.overlay import Overlay

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 3)


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """done・遅れ達成・未来・遅れ作業・今後 の各 1 件がそろう、lint に通る木。"""
    ep = root / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    # 期日 08-28 を 09-05 に達成（closed>due＝遅れて達成）
    _write(
        ep / "T-9005-mid.md",
        {
            "id": "T-9005",
            "kind": "task",
            "status": "done",
            "due": "2026-08-28",
            "milestone": True,
            "created": "2026-08-01",
            "closed": "2026-09-05",
        },
    )
    _write(
        ep / "T-9006-final.md",
        {"id": "T-9006", "kind": "task", "status": "todo", "due": "2026-09-30", "milestone": True},
    )
    _write(
        ep / "T-9002-collect.md",
        {
            "id": "T-9002",
            "kind": "task",
            "status": "in-progress",
            "start": "2026-08-17",
            "due": "2026-08-28",
            "team": "データ",
            "owner": "鈴木",
        },
    )
    _write(
        ep / "T-9003-feat.md",
        {
            "id": "T-9003",
            "kind": "task",
            "status": "todo",
            "start": "2026-09-07",
            "due": "2026-09-11",
            "team": "データ",
            "owner": "高橋",
        },
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _report(root: Path, today: date = TODAY, **kw: Any) -> str:
    return report_mod.render_report(wbs_mod.build(root, today=today, overlay=Overlay()), today=today, **kw)


def test_milestones_are_split_into_achieved_late_and_planned(tmp_path: Path) -> None:
    """達成／遅れ／予定 の 3 区分に分かれる。期日超過の達成は予定と実績の両方を出す（粉飾しない）。"""
    _scaffold(tmp_path)
    html = _report(tmp_path)
    ms = html.split("マイルストーンの状況")[1].split("</section>")[0]
    # T-9005 は closed(09-05) > due(08-28) ＝「遅れて達成」で予定と実績の両日付が出る（「達成」で塗り潰さない）。
    assert "遅れて達成" in ms
    assert "予定 2026-08-28 → 実績 2026-09-05" in ms
    assert "達成" not in ms.replace("遅れて達成", "")  # 期日超過が無印の「達成」に化けない
    # T-9006 は未来＝予定。
    assert "予定" in ms and "2026-09-30" in ms


def test_an_on_time_milestone_reads_as_achieved(tmp_path: Path) -> None:
    """期日内に閉じたマイルストーンは「達成」＋実績日で出る。"""
    ep = tmp_path / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        ep / "T-1-m.md",
        {
            "id": "T-0001",
            "kind": "task",
            "status": "done",
            "due": "2026-08-28",
            "milestone": True,
            "created": "2026-08-01",
            "closed": "2026-08-27",
        },
    )
    _write(
        ep / "T-2-t.md", {"id": "T-0002", "kind": "task", "status": "todo", "start": "2026-09-01", "due": "2026-09-05"}
    )
    ms = _report(tmp_path).split("マイルストーンの状況")[1].split("</section>")[0]
    assert "達成" in ms and "遅れて達成" not in ms
    assert "実績 2026-08-27" in ms


def test_zero_count_sections_say_so(tmp_path: Path) -> None:
    """遅れ 0 件は「遅れなし」、今後 0 件は「該当なし」と明記する（黙って消さない）。"""
    ep = tmp_path / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    # 遅れも今後もない：はるか未来の作業 1 件だけ（窓 14 日の外）。
    _write(
        ep / "T-1-t.md", {"id": "T-0001", "kind": "task", "status": "todo", "start": "2026-12-01", "due": "2026-12-05"}
    )
    html = _report(tmp_path)
    assert "遅れなし" in html.split("遅れている作業")[1].split("</section>")[0]
    assert "該当なし" in html.split("今後 14 日の予定")[1].split("</section>")[0]


def test_late_work_lists_the_overrun_days(tmp_path: Path) -> None:
    """遅れている作業に予定終了と超過日数（today−due）が出る。"""
    _scaffold(tmp_path)
    late = _report(tmp_path).split("遅れている作業")[1].split("</section>")[0]
    assert "T-9002" in late and "2026-08-28" in late and "6 日超過" in late  # 09-03 − 08-28 = 6


def test_the_change_section_shows_the_commit_that_moved_a_date(tmp_path: Path) -> None:
    """--against で、前回からの日程変化がその変化を入れたコミット件名つきで出る（テストデータ由来の値で確認）。"""
    _scaffold(tmp_path)
    _git(tmp_path, "init", "-q")
    agreed = _commit(tmp_path, "init")
    post = frontmatter.load(tmp_path / "work" / "EP-90-x" / "T-9003-feat.md")
    post["due"] = "2026-09-18"  # 09-11 → 09-18 に後ろ倒し
    (tmp_path / "work" / "EP-90-x" / "T-9003-feat.md").write_text(frontmatter.dumps(post), encoding="utf-8")
    _commit(tmp_path, "T-9003 予定終了を後ろ倒し")
    result = CliRunner().invoke(
        wbs_app,
        [
            "report",
            "--root",
            str(tmp_path),
            "--against",
            agreed,
            "--out",
            str(tmp_path / "R.html"),
            "--today",
            TODAY.isoformat(),
        ],
    )
    assert result.exit_code == 0, result.output
    change = (tmp_path / "R.html").read_text(encoding="utf-8").split("前回からの変化")[1].split("</section>")[0]
    assert "2026-09-11" in change and "2026-09-18" in change  # 前後の日付
    assert "後ろ倒し" in change  # 変化を入れたコミット件名


def test_report_refuses_like_export(tmp_path: Path) -> None:
    """report の拒否は export と同じ関門を通る：検査失敗・日程 0 件・未コミットで出力しない。"""
    runner = CliRunner()
    # 日程 0 件
    _write(tmp_path / "work" / "EP-1" / "item.md", {"id": "EP-1", "kind": "epic", "status": "todo"})
    out = tmp_path / "R.html"
    r0 = runner.invoke(wbs_app, ["report", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()])
    assert r0.exit_code == 1 and not out.exists()
    # 未コミット（git 有り・dirty）
    _scaffold(tmp_path)
    _git(tmp_path, "init", "-q")
    _commit(tmp_path, "init")
    _write(
        tmp_path / "work" / "EP-90-x" / "T-9003-feat.md",
        {"id": "T-9003", "kind": "task", "status": "todo", "start": "2026-09-07", "due": "2026-09-20"},
    )
    r1 = runner.invoke(wbs_app, ["report", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat()])
    assert r1.exit_code == 1 and not out.exists()  # 未コミットは拒否
    r2 = runner.invoke(
        wbs_app, ["report", "--root", str(tmp_path), "--out", str(out), "--today", TODAY.isoformat(), "--draft"]
    )
    assert r2.exit_code == 0 and out.exists()  # --draft なら出る


def _write_req(root: Path, req_id: str) -> None:
    (root / "docs" / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "requirements" / f"{req_id}.md").write_text(
        f"---\nid: {req_id}\nkind: functional\nstatus: accepted\nsatisfies: []\n---\n# {req_id}\n", encoding="utf-8"
    )


def test_the_requirement_trace_shows_coverage_and_gaps(tmp_path: Path) -> None:
    """要件トレース節：REQ→作業→状態が出て、作業ゼロの REQ は「未カバーの要件」として穴が出る。

    被覆集合は lint（pm.check）の未カバー info と同じ導出（requirement_trace）を見る＝表と検査が食い違わない。
    """
    from harness import pm

    ep = tmp_path / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        ep / "T-1.md",
        {
            "id": "T-0001",
            "kind": "task",
            "status": "done",
            "start": "2026-08-03",
            "due": "2026-08-07",
            "requirements": ["REQ-001"],
        },
    )
    _write(
        ep / "T-2.md", {"id": "T-0002", "kind": "task", "status": "todo", "start": "2026-09-01", "due": "2026-09-05"}
    )
    _write_req(tmp_path, "REQ-001")
    _write_req(tmp_path, "REQ-002")  # どの作業からも参照されない＝未カバー
    trace = pm.requirement_trace(tmp_path)
    html = _report(tmp_path, trace=trace)
    sec = html.split("要件トレース")[1].split("</section>")[0]
    assert "REQ-001" in sec and "T-0001" in sec and "完了" in sec  # 要件→作業→状態
    assert "REQ-002" in sec and "未カバーの要件" in sec  # 作業ゼロの穴
    # 被覆ビューの未カバー集合と lint の未カバー info が一致（同じ導出を見ている）。
    assert trace.uncovered == ["REQ-002"]


def test_the_trace_section_is_omitted_without_a_requirements_layer(tmp_path: Path) -> None:
    """要件文書が無い案件では要件トレース節を出さない（空表を出さない）。"""
    _scaffold(tmp_path)
    html = _report(tmp_path, trace=None)
    assert "要件トレース" not in html


def test_user_text_is_escaped_in_the_report(tmp_path: Path) -> None:
    """利用者由来の文字列（作業名）は報告でもエスケープする。"""
    ep = tmp_path / "work" / "EP-90-x"
    _write(ep / "item.md", {"id": "EP-90", "kind": "epic", "status": "todo", "plan": "detailed"})
    _write(
        ep / "T-1-x.md",
        {
            "id": "T-0001",
            "kind": "task",
            "status": "todo",
            "title": "<script>alert(1)</script>",
            "start": "2026-09-01",
            "due": "2026-09-05",
        },
    )
    html = _report(tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_the_report_reads_nothing_from_outside(tmp_path: Path) -> None:
    """報告も自己完結（外部リソース参照ゼロ＝そのまま送れる）。"""
    import re

    _scaffold(tmp_path)
    html = _report(tmp_path)
    assert re.search(r"https?://|<link\b|<script\b[^>]*\bsrc=|<img\b", html) is None
