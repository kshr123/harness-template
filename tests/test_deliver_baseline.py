"""合意した時点との差のテスト。

差の中身だけでなく、**動いていない単位が出てこない**ことを確かめる（全部並べる報告は読まれない）。
理由を別の場所に書き写さず、その日程を動かしたコミットをそのまま添えていることも見る。
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest
from typer.testing import CliRunner

from harness.deliver import baseline
from harness.deliver.cli import wbs_app

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)
AGREED = "agreed"  # 合意した時点に打つ印（タグ）


def _write(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("")
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip()


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "-c", "core.hooksPath=/dev/null", "commit", "-qm", message, "--no-verify")


@pytest.fixture
def agreed_project(tmp_path: Path) -> Path:
    """合意した時点（タグ agreed）まで作ったリポジトリ。2 件のタスクが両方 08 月に載っている。"""
    alpha = tmp_path / "work" / "EP-90-alpha"
    _write(alpha / "item.md", {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(
        alpha / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "title": "設計", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _write(
        alpha / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-10", "due": "2026-08-12"},
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _commit(tmp_path, "EP-90 T-9001：合意した計画")
    _git(tmp_path, "tag", AGREED)
    return tmp_path


def test_nothing_moved_means_no_changes(agreed_project: Path) -> None:
    assert baseline.changes_since(agreed_project, AGREED, today=TODAY) == []


def test_a_moved_date_appears_with_the_commit_that_moved_it(agreed_project: Path) -> None:
    """動いた単位だけが出て、その変更を入れたコミットが添えられる（理由を書き写さない）。"""
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9002：先方のデータ提供が遅れたため実装を 1 週間後ろへ")

    changes = baseline.changes_since(agreed_project, AGREED, today=TODAY)
    moved = {(c.ref, c.kind): c for c in changes}
    # 動かした単位そのものと、その結果として終わりがずれた親だけが出る（動かしていない T-9001 は出ない）。
    assert set(moved) == {("T-9002", "予定開始"), ("T-9002", "予定終了"), ("EP-90", "予定終了")}
    start = moved[("T-9002", "予定開始")]
    assert (start.before, start.after) == ("2026-08-10", "2026-08-17")
    assert start.commits and "先方のデータ提供が遅れた" in start.commits[0]
    assert "2026-08-10 → 2026-08-17" in start.line()
    # 親は自分で動いたのではないと分かる形にする（同じ事実を 2 回主張しない）。
    parent = moved[("EP-90", "予定終了")]
    assert parent.derived and not parent.commits
    assert "配下の変更による" in parent.line()
    assert not start.derived


def test_added_and_removed_units_are_listed(agreed_project: Path) -> None:
    (agreed_project / "work" / "EP-90-alpha" / "T-9001-a.md").unlink()
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9003-c.md",
        {
            "id": "T-9003",
            "kind": "task",
            "status": "todo",
            "title": "追加作業",
            "start": "2026-08-24",
            "due": "2026-08-28",
        },
    )
    _commit(agreed_project, "EP-90 T-9003：スコープの入れ替え")

    kinds = {(c.ref, c.kind) for c in baseline.changes_since(agreed_project, AGREED, today=TODAY)}
    assert ("T-9001", "削除") in kinds
    assert ("T-9003", "追加") in kinds


def test_a_status_change_is_reported(agreed_project: Path) -> None:
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "done", "title": "設計", "start": "2026-08-03", "due": "2026-08-07"},
    )
    _commit(agreed_project, "EP-90 T-9001：設計を完了にする")
    changes = {
        (c.ref, c.kind): (c.before, c.after) for c in baseline.changes_since(agreed_project, AGREED, today=TODAY)
    }
    assert changes[("T-9001", "状態")] == ("todo", "done")


def test_the_working_tree_is_left_alone(agreed_project: Path) -> None:
    """比較のために作業ツリーを切り替えない（いまの作業を邪魔しない）。"""
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9002：後ろへ")
    before = (agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md").read_text(encoding="utf-8")
    baseline.changes_since(agreed_project, AGREED, today=TODAY)
    assert (agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md").read_text(encoding="utf-8") == before
    assert _git(agreed_project, "status", "--porcelain") == ""


def test_an_unknown_reference_fails_loudly(agreed_project: Path) -> None:
    with pytest.raises(baseline.BaselineError):
        baseline.changes_since(agreed_project, "そんなタグは無い", today=TODAY)


def test_the_diff_command_reports_and_says_when_nothing_moved(agreed_project: Path) -> None:
    runner = CliRunner()
    quiet = runner.invoke(wbs_app, ["diff", AGREED, "--root", str(agreed_project), "--today", TODAY.isoformat()])
    assert quiet.exit_code == 0, quiet.output
    assert "動いていない" in quiet.output

    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9002：後ろ倒し")
    loud = runner.invoke(wbs_app, ["diff", AGREED, "--root", str(agreed_project), "--today", TODAY.isoformat()])
    assert loud.exit_code == 0, loud.output
    assert "T-9002" in loud.output
    assert "後ろ倒し" in loud.output


def test_the_diff_command_fails_on_an_unknown_reference(agreed_project: Path) -> None:
    result = CliRunner().invoke(wbs_app, ["diff", "無い印", "--root", str(agreed_project)])
    assert result.exit_code == 1


def test_export_at_a_past_reference_reproduces_that_plan(agreed_project: Path) -> None:
    """合意した時点を指定すると、その時点の WBS をそのまま出し直せる（いまの値が混ざらない）。"""
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9002：後ろへ")
    out = agreed_project / "past.html"
    result = CliRunner().invoke(
        wbs_app,
        ["export", "--root", str(agreed_project), "--out", str(out), "--today", TODAY.isoformat(), "--at", AGREED],
    )
    assert result.exit_code == 0, result.output
    page = out.read_text(encoding="utf-8")
    assert "08/12" in page  # 合意した時点の予定終了
    assert "08/21" not in page  # いまの予定終了は混ざらない
    assert f"コミット {AGREED}" in page  # 刻むのはその時点（いまの HEAD ではない）


def test_export_at_a_past_reference_ignores_uncommitted_changes(agreed_project: Path) -> None:
    """過去の時点を出すときは、未コミットの変更があっても拒否しない（その変更は出力に入らないため）。"""
    (agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md").write_text(
        "---\nid: T-9002\nkind: task\nstatus: todo\nstart: 2026-09-01\ndue: 2026-09-02\n---\n", encoding="utf-8"
    )
    out = agreed_project / "past.html"
    result = CliRunner().invoke(
        wbs_app,
        ["export", "--root", str(agreed_project), "--out", str(out), "--today", TODAY.isoformat(), "--at", AGREED],
    )
    assert result.exit_code == 0, result.output
    assert "09/02" not in out.read_text(encoding="utf-8")


def test_the_reason_is_the_commit_that_changed_that_field(agreed_project: Path) -> None:
    """理由として添えるのは「その欄を実際に変えたコミット」。

    「そのファイルを最後に触ったコミット」で代用すると、日付を動かした後に担当欄を直しただけの
    コミットが日付変更の理由として出る＝クライアントへの説明に嘘の理由が刻まれる。
    """
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9001-a.md",
        {"id": "T-9001", "kind": "task", "status": "todo", "title": "設計", "start": "2026-08-03", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9001：先方レビューの遅延で終了を後ろへ")
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9001-a.md",
        {
            "id": "T-9001",
            "kind": "task",
            "status": "todo",
            "title": "設計",
            "start": "2026-08-03",
            "due": "2026-08-21",
            "owner": "山田",
        },
    )
    _commit(agreed_project, "EP-90 T-9001：担当を山田にする")

    moved = {(c.ref, c.kind): c for c in baseline.changes_since(agreed_project, AGREED, today=TODAY)}
    due = moved[("T-9001", "予定終了")]
    assert due.commits, "理由のコミットが添えられていない"
    assert "先方レビューの遅延" in due.commits[0]
    assert all("担当を山田" not in c for c in due.commits)  # 日付を動かしていないコミットは理由にしない


def test_a_client_facing_phase_shows_its_own_movement(agreed_project: Path) -> None:
    """節（顧客向けのフェーズ）の日程が動いたことも出る。フェーズの終わりはクライアントが最も見る。"""
    (agreed_project / "docs").mkdir(exist_ok=True)
    (agreed_project / "docs" / "wbs.yaml").write_text(
        "sections:\n  - name: フェーズ1\n    entries:\n      - work: EP-90\n", encoding="utf-8"
    )
    _commit(agreed_project, "EP-90 T-9001：顧客向けの節を置く")
    _git(agreed_project, "tag", "節あり合意")  # 節がある状態を合意した時点にする
    _write(
        agreed_project / "work" / "EP-90-alpha" / "T-9002-b.md",
        {"id": "T-9002", "kind": "task", "status": "todo", "title": "実装", "start": "2026-08-17", "due": "2026-08-21"},
    )
    _commit(agreed_project, "EP-90 T-9002：後ろへ")

    kinds = {(c.ref, c.kind) for c in baseline.changes_since(agreed_project, "節あり合意", today=TODAY)}
    assert ("節 フェーズ1", "予定終了") in kinds


def test_a_parent_title_change_is_not_called_a_consequence(agreed_project: Path) -> None:
    """親の表題は親自身に保存された値なので、「配下の変更による」とは言わない（理由も添える）。"""
    _write(
        agreed_project / "work" / "EP-90-alpha" / "item.md",
        {"id": "EP-90", "kind": "epic", "status": "in-progress", "plan": "detailed", "title": "基本設計"},
    )
    _commit(agreed_project, "EP-90 T-9001：フェーズ名を先方の言い方に合わせる")
    moved = {(c.ref, c.kind): c for c in baseline.changes_since(agreed_project, AGREED, today=TODAY)}
    change = moved[("EP-90", "表題")]
    assert not change.derived
    assert change.commits and "先方の言い方" in change.commits[0]
