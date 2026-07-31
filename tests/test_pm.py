"""プロジェクト管理の中核ロジックのテスト。

作る側（pm）と確かめる側（テスト）を分け、期待する動きをテストで固定する。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from harness import pm

pytestmark = pytest.mark.unit


def _write(path: Path, meta: dict[str, object], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    """EP-01（詳しく分解済み・子タスク2件）と EP-02（未分解）を作る。"""
    # done タスクが指す先＝実在するテスト（完了↔検証の結びつけ）。
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    ep1 = root / "work" / "EP-01-foundation"
    _write(
        ep1 / "item.md", {"id": "EP-01", "kind": "epic", "status": "in-progress", "plan": "detailed", "title": "基盤"}
    )
    t1: dict[str, object] = {"id": "T-0001", "kind": "task", "status": "done"}
    t1["verified_by"] = ["tests/test_a.py::test_a"]
    _write(ep1 / "T-0001-a.md", t1)
    t2: dict[str, object] = {"id": "T-0002", "kind": "task", "status": "todo", "depends_on": ["T-0001"]}
    _write(ep1 / "T-0002-b.md", t2)
    ep2 = root / "work" / "EP-02-dev"
    _write(ep2 / "item.md", {"id": "EP-02", "kind": "epic", "status": "todo", "plan": "outline", "title": "開発ループ"})


def test_outline_epic_without_children_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # EP-02 は未分解（outline・子なし）でも失敗にしない。
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_duplicate_id_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 同じ ID をもう 1 つ作る＝重複＝失敗。
    dup: dict[str, object] = {"id": "T-0001", "kind": "task", "status": "todo"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0001-dup.md", dup)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("重複" in p.message for p in errors)


def test_dangling_depends_on_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 存在しない単位に依存＝参照エラー＝失敗。
    x: dict[str, object] = {"id": "T-0009", "kind": "task", "status": "todo", "depends_on": ["T-9999"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0009-x.md", x)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("T-9999" in p.message for p in errors)


def test_schedule_start_after_due_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 予定開始が予定終了より後＝矛盾＝失敗（日付は任意だが、置いたら整合を要求する）。
    bad: dict[str, object] = {
        "id": "T-0010",
        "kind": "task",
        "status": "todo",
        "start": "2026-03-10",
        "due": "2026-03-01",
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0010-bad.md", bad)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("T-0010" in p.message and "start" in p.message for p in errors)


def test_schedule_valid_dates_are_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    ok: dict[str, object] = {
        "id": "T-0011",
        "kind": "task",
        "status": "todo",
        "start": "2026-03-01",
        "due": "2026-03-10",
        "effort_days": 5,
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0011-ok.md", ok)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert not any("T-0011" in p.message for p in errors)


def test_negative_effort_days_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 見積り工数は正の値のみ（負の人日は矛盾）＝検証で失敗（保証 (a)。frontmatter 不正として error）。
    bad: dict[str, object] = {"id": "T-0013", "kind": "task", "status": "todo", "effort_days": -3}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0013-neg.md", bad)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("T-0013" in p.message for p in errors)


def test_milestone_without_due_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # マイルストーンは期日を持つ＝due 無しは失敗（ガントに置けない・合意点にならない）。
    ms: dict[str, object] = {"id": "T-0012", "kind": "task", "status": "todo", "milestone": True}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0012-ms.md", ms)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("T-0012" in p.message and "milestone" in p.message for p in errors)


def test_done_task_without_verified_by_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # done なのに対応するテスト（verified_by）が無い＝失敗（自己申告完了を防ぐ）。
    d: dict[str, object] = {"id": "T-0003", "kind": "task", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0003-d.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("verified_by" in p.message for p in errors)


def test_done_task_with_missing_test_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # verified_by が実在しないテストを指す＝失敗。
    d: dict[str, object] = {"id": "T-0004", "kind": "task", "status": "done", "verified_by": ["tests/nope.py::x"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0004-e.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("nope.py" in p.message for p in errors)


def test_verified_by_missing_named_test_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # ファイルは在るが、その中に無いテスト名（::名）を指す＝失敗（穴埋め(b) の強化）。
    d: dict[str, object] = {
        "id": "T-0007",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_a.py::test_missing"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0007-g.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("test_missing" in p.message for p in errors)


def test_verified_by_present_named_test_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # ::名 がファイル本文に在れば通る（test_a.py には def test_a がある）。
    d: dict[str, object] = {
        "id": "T-0008",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_a.py::test_a"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0008-h.md", d)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0008" in p.message]


def test_verified_by_file_only_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # ::テスト名 を必須化した。ファイル名だけの参照は「実在する無関係なファイル」でも通ってしまうため error。
    d: dict[str, object] = {"id": "T-0011", "kind": "task", "status": "done", "verified_by": ["tests/test_a.py"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0011-i.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0011" in p.message]
    assert any("::テスト名" in p.message for p in errors)


def test_verified_by_unrelated_real_file_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 実在するが無関係なファイルを :: 無しで指しても、実在照合されず通ってしまう欠陥を塞ぐ（::必須で error）。
    (tmp_path / "tests" / "test_unrelated.py").write_text("def test_other():\n    pass\n", encoding="utf-8")
    d: dict[str, object] = {
        "id": "T-0012",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_unrelated.py"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0012-j.md", d)
    assert [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0012" in p.message]


def test_verified_by_comment_only_test_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 素朴な \b名前\b の本文照合だと、コメント行だけのファイルで done が通ってしまう（実測済みの欠陥）。
    # ast 照合なら def 定義でない名前（コメント・文字列）は当たらない＝error。
    (tmp_path / "tests" / "test_stub.py").write_text("# TODO: test_acceptance を書く予定\n", encoding="utf-8")
    d: dict[str, object] = {
        "id": "T-0013",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_stub.py::test_acceptance"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0013-k.md", d)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0013" in p.message]
    assert any("test_acceptance" in p.message for p in errors)


def test_verified_by_string_literal_named_test_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 文字列の中にテスト名が現れるだけ（def 定義ではない）＝ast では当たらない＝error。
    (tmp_path / "tests" / "test_str.py").write_text(
        'NAME = "test_acceptance"\n\ndef test_real():\n    assert True\n', encoding="utf-8"
    )
    d: dict[str, object] = {
        "id": "T-0014",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_str.py::test_acceptance"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0014-l.md", d)
    assert [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0014" in p.message]


def test_verified_by_class_method_form_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # tests/test_x.py::TestClass::test_y（クラス内メソッド）の nodeid 形にも対応する。
    (tmp_path / "tests" / "test_cls.py").write_text(
        "class TestGroup:\n    def test_inside(self):\n        assert True\n", encoding="utf-8"
    )
    d: dict[str, object] = {
        "id": "T-0015",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_cls.py::TestGroup::test_inside"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0015-m.md", d)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0015" in p.message]


def test_verified_by_class_method_missing_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # クラスは在るが、そのメソッドが無い（別クラスの同名メソッドもない）＝error。
    (tmp_path / "tests" / "test_cls2.py").write_text(
        "class TestGroup:\n    def test_inside(self):\n        assert True\n", encoding="utf-8"
    )
    d: dict[str, object] = {
        "id": "T-0016",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_cls2.py::TestGroup::test_absent"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0016-n.md", d)
    assert [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0016" in p.message]


def test_verified_by_parametrized_id_matches_base_name(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # パラメータ化の [..] は落として素の名前で照合する（test_a[case1] → test_a）。
    d: dict[str, object] = {
        "id": "T-0017",
        "kind": "task",
        "status": "done",
        "verified_by": ["tests/test_a.py::test_a[case1]"],
    }
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0017-o.md", d)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "T-0017" in p.message]


def test_work_tree_orphan_dir_hides_unit_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # item.md の無いディレクトリ配下の単位は、木をたどる pm.lint からは不可視になる（verified_by 無しの
    # done も素通りする）。work_tree_lint はファイルシステムを走査して、この不可視領域を error にする。
    orphan: dict[str, object] = {"id": "T-0400", "kind": "task", "status": "done"}  # verified_by 無し
    _write(tmp_path / "work" / "EP-01-foundation" / "sub" / "T-0400-x.md", orphan)
    errors = [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]
    assert any("item.md" in p.message and "sub" in p.message for p in errors)
    # 統合：pm.lint 経由でも同じ error が出る（INVARIANT_CHECKS に載る）。
    assert any("sub" in p.message for p in pm.lint(tmp_path) if p.level == "error")


def test_work_tree_unknown_md_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 作業単位の命名にも成果物のファイル名にも一致しない .md（例 T0001.md＝ハイフン無し）＝正体不明＝error。
    (tmp_path / "work" / "EP-01-foundation" / "T0001.md").write_text("正体不明\n", encoding="utf-8")
    errors = [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]
    assert any("T0001.md" in p.message and "正体不明" in p.message for p in errors)


def test_work_tree_artifact_md_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 成果物（SPEC/PLAN/DESIGN/notes/README）は許容される（黙認ではなく既知の成果物）。
    (tmp_path / "work" / "EP-01-foundation" / "DESIGN.md").write_text("# 設計メモ\n", encoding="utf-8")
    (tmp_path / "work" / "EP-01-foundation" / "notes.md").write_text("メモ\n", encoding="utf-8")
    assert not [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]


def test_next_actionable_classifies_ready_waiting_and_outline(tmp_path: Path) -> None:
    """next_actionable は「着手できる」「依存待ち」「分解候補」を構成から分ける。"""
    ep = tmp_path / "work" / "EP-10-x"
    _write(ep / "item.md", {"id": "EP-10", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    # T-1（done）→ T-2 は依存が満たされている＝ready。T-3 は未完の T-4 に依存＝waiting。
    verified = ["tests/test_pm.py::test_next_actionable_classifies_ready_waiting_and_outline"]
    _write(ep / "T-0501-done.md", {"id": "T-0501", "kind": "task", "status": "done", "verified_by": verified})
    _write(ep / "T-0502-ready.md", {"id": "T-0502", "kind": "task", "status": "todo", "depends_on": ["T-0501"]})
    _write(ep / "T-0503-wait.md", {"id": "T-0503", "kind": "task", "status": "todo", "depends_on": ["T-0504"]})
    _write(ep / "T-0504-blocker.md", {"id": "T-0504", "kind": "task", "status": "todo"})
    # outline のままの epic（子なし）＝分解候補。
    _write(
        tmp_path / "work" / "EP-11-y" / "item.md",
        {"id": "EP-11", "kind": "epic", "status": "todo", "plan": "outline"},
    )

    in_progress, ready, waiting, to_outline = pm.next_actionable(tmp_path)
    ready_ids = {n.item.id for n in ready}
    waiting_ids = {n.item.id for n, _ in waiting}
    outline_ids = {n.item.id for n in to_outline}
    # T-0502（依存 done）と T-0504（依存なし）は着手可能。T-0503 は依存 T-0504 が未完＝待ち。
    assert ready_ids == {"T-0502", "T-0504"}
    assert waiting_ids == {"T-0503"}
    assert "T-0504" in [d for n, unmet in waiting if n.item.id == "T-0503" for d in unmet]
    assert outline_ids == {"EP-11"}
    # done タスク・分解済み epic（EP-10）は着手候補に出ない。この構成に in-progress の末端は無い。
    assert "T-0501" not in ready_ids and "EP-10" not in outline_ids
    assert in_progress == []


def test_next_actionable_orders_ready_by_priority_then_id(tmp_path: Path) -> None:
    """ready の並びは優先度（人が置く判断）→ID。優先度を置いた単位だけが上下し、無指定は ID 順のまま。"""
    ep = tmp_path / "work" / "EP-12-p"
    _write(ep / "item.md", {"id": "EP-12", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    # ID 順なら A<B<C<D だが、優先度で D(high) が先頭、B(low) が末尾に来る。C・A は無指定＝中位で ID 順。
    _write(ep / "T-0601-a.md", {"id": "T-0601", "kind": "task", "status": "todo"})
    _write(ep / "T-0602-b.md", {"id": "T-0602", "kind": "task", "status": "todo", "priority": "low"})
    _write(ep / "T-0603-c.md", {"id": "T-0603", "kind": "task", "status": "todo"})
    _write(ep / "T-0604-d.md", {"id": "T-0604", "kind": "task", "status": "todo", "priority": "high"})

    _, ready, _, _ = pm.next_actionable(tmp_path)
    assert [n.item.id for n in ready] == ["T-0604", "T-0601", "T-0603", "T-0602"]


def test_next_actionable_lists_in_progress_leaves(tmp_path: Path) -> None:
    """仕掛かり中（in-progress の末端 task/experiment/investigation）は再開の候補として可視化する。

    investigation も末端の作業単位なので放置の可視化から漏らさない（分解済み epic はコンテナなので出さない）。
    """
    ep = tmp_path / "work" / "EP-13-r"
    # 末端でない in-progress epic は「仕掛かり中」に出さない（分解済みコンテナ）。
    _write(ep / "item.md", {"id": "EP-13", "kind": "epic", "status": "in-progress", "plan": "detailed"})
    _write(ep / "T-0701-wip.md", {"id": "T-0701", "kind": "task", "status": "in-progress"})
    _write(ep / "INV-0701-probe.md", {"id": "INV-0701", "kind": "investigation", "status": "in-progress"})
    _write(ep / "T-0702-todo.md", {"id": "T-0702", "kind": "task", "status": "todo"})

    in_progress, ready, _, _ = pm.next_actionable(tmp_path)
    # task と investigation の両方が再開候補に出る（ID 順）。分解済み epic EP-13 は出ない。
    assert [n.item.id for n in in_progress] == ["INV-0701", "T-0701"]
    assert [n.item.id for n in ready] == ["T-0702"]


def test_next_actionable_orders_outline_epics_by_priority(tmp_path: Path) -> None:
    """分解の候補（outline epic）も priority→ID で並べる＝epic に置いた優先度も静かに捨てない。"""
    _write(
        tmp_path / "work" / "EP-15-a" / "item.md",
        {"id": "EP-15", "kind": "epic", "status": "todo", "plan": "outline"},
    )
    _write(
        tmp_path / "work" / "EP-16-b" / "item.md",
        {"id": "EP-16", "kind": "epic", "status": "todo", "plan": "outline", "priority": "high"},
    )
    _, _, _, to_outline = pm.next_actionable(tmp_path)
    # ID 順なら EP-15<EP-16 だが、EP-16 が high なので先頭に来る。
    assert [n.item.id for n in to_outline] == ["EP-16", "EP-15"]


def test_invalid_priority_value_is_rejected(tmp_path: Path) -> None:
    """優先度は列挙（high/normal/low）＝未知の自由文字列は検証で失敗する（保証 (a)。タイポは done にならない）。"""
    ep = tmp_path / "work" / "EP-14-bad"
    _write(ep / "item.md", {"id": "EP-14", "kind": "epic", "status": "todo", "plan": "outline"})
    _write(ep / "T-0801-x.md", {"id": "T-0801", "kind": "task", "status": "todo", "priority": "urgent"})
    problems = pm.lint(tmp_path)
    assert any("T-0801" in p.message or "priority" in p.message.lower() for p in problems if p.level == "error")


def test_status_cli_writes_file_by_default_and_next_flag_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """console_script の入口を CliRunner で叩く：既定は STATUS.md を書き、--next は書かず提案を出す。

    回帰：素の関数を console_script にして typer.Option を既定値に置くと OptionInfo が truthy に評価され、
    --next 無しでも提案の枝に入って STATUS.md を書かなくなる（typer.run で包まないと argv が解釈されない）。
    """
    import typer
    from typer.testing import CliRunner

    from harness import cli

    _scaffold(tmp_path)  # EP-01（T-0001 done・T-0002 todo）＋EP-02（outline）を作る
    monkeypatch.chdir(tmp_path)
    app = typer.Typer()
    app.command()(cli.status_cmd)  # console_script の本体をそのまま CliRunner に載せる
    runner = CliRunner()

    result = runner.invoke(app, [])  # 既定＝STATUS.md を生成
    assert result.exit_code == 0
    assert (tmp_path / "STATUS.md").is_file()
    (tmp_path / "STATUS.md").unlink()

    result_next = runner.invoke(app, ["--next"])  # --next＝提案を出し STATUS.md は書かない
    assert result_next.exit_code == 0
    assert "次に着手できる" in result_next.stdout
    assert not (tmp_path / "STATUS.md").exists()


def test_work_tree_nested_unit_with_item_chain_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # item.md を持つ子ディレクトリ配下の単位は見える（鎖が work/ まで続く）＝error にしない。
    _write(
        tmp_path / "work" / "EP-01-foundation" / "E-0009-exp" / "item.md",
        {"id": "E-0009", "kind": "experiment", "status": "todo"},
    )
    _write(
        tmp_path / "work" / "EP-01-foundation" / "E-0009-exp" / "T-0401-a.md",
        {"id": "T-0401", "kind": "task", "status": "todo"},
    )
    assert not [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]


def test_work_tree_orphan_dir_hides_directory_unit_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # ディレクトリ単位（item.md）も、途中の階層に item.md が欠けると不可視になる（軽い単位と同じ穴）。
    # MIDDLE に item.md が無いので、その奥の E-0009-exp/item.md（と配下）は全 PM 検査から消える。
    _write(
        tmp_path / "work" / "EP-01-foundation" / "MIDDLE" / "E-0009-exp" / "item.md",
        {"id": "E-0009", "kind": "experiment", "status": "done"},  # verified_by 無しの done も消える
    )
    errors = [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]
    assert any("item.md" in p.message and "E-0009-exp" in p.message for p in errors)
    # 統合：pm.lint 経由でも同じ error が出る。
    assert any("E-0009-exp" in p.message for p in pm.lint(tmp_path) if p.level == "error")


def test_work_tree_lightweight_unit_directly_in_work_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # work/ 直下の軽い単位ファイルは、work/ が木の起点なので見える＝error にしない。
    _write(tmp_path / "work" / "T-0402-loose.md", {"id": "T-0402", "kind": "task", "status": "todo"})
    assert not [p for p in pm.work_tree_lint(tmp_path) if p.level == "error"]


def test_experiment_done_without_results_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # done の実験に結果記録（results/）が無い＝失敗（穴埋め(a)・調査の「## 結論」と同型）。
    e: dict[str, object] = {"id": "E-0001", "kind": "experiment", "status": "done", "plan": "detailed"}
    _write(tmp_path / "work" / "EP-01-foundation" / "E-0001-exp" / "item.md", e)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error" and "E-0001" in p.message]
    assert errors


def test_experiment_done_with_results_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    d = tmp_path / "work" / "EP-01-foundation" / "E-0002-exp"
    _write(d / "item.md", {"id": "E-0002", "kind": "experiment", "status": "done", "plan": "detailed"})
    (d / "results").mkdir(parents=True)
    (d / "results" / "metrics.yaml").write_text("auc: 0.5\n", encoding="utf-8")
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "E-0002" in p.message]


def test_experiment_todo_needs_no_results(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # まだ done でない実験は結果記録を要求されない。
    _write(
        tmp_path / "work" / "EP-01-foundation" / "E-0003-exp" / "item.md",
        {"id": "E-0003", "kind": "experiment", "status": "todo", "plan": "detailed"},
    )
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "E-0003" in p.message]


def test_make_project_builds_lintable_project(make_project: Callable[..., Any]) -> None:
    # conftest の工場が、検査を通る一時プロジェクトを組み立てられること（フィクスチャの結線確認）。
    proj = make_project()
    proj.add_file("tests/test_x.py", "def test_x():\n    assert True\n")
    proj.add_item(
        "work/EP-09/item.md",
        {"id": "EP-09", "kind": "epic", "status": "in-progress", "plan": "detailed", "title": "サンプル"},
    )
    proj.add_item(
        "work/EP-09/T-0100-a.md",
        {"id": "T-0100", "kind": "task", "status": "done", "verified_by": ["tests/test_x.py::test_x"]},
    )
    assert not [p for p in pm.lint(proj.root) if p.level == "error"]


def test_epic_title_required_when_not_done(tmp_path: Path) -> None:
    # done でないエピックは title 必須（status・クライアント向け WBS の行名になるため）。
    ep: dict[str, object] = {"id": "EP-10", "kind": "epic", "status": "todo", "plan": "outline"}
    _write(tmp_path / "work" / "EP-10/item.md", ep)
    assert any("EP-10" in p.message and "title が無い" in p.message for p in pm.lint(tmp_path))


def test_epic_title_present_passes_and_done_and_tasks_are_grandfathered(tmp_path: Path) -> None:
    # title 付き→通る／done エピックは title 無しでも見逃す（grandfather）／タスクは対象外（推奨止まり）。
    _write(
        tmp_path / "work" / "EP-11/item.md",
        {"id": "EP-11", "kind": "epic", "status": "todo", "plan": "outline", "title": "新機能"},
    )
    _write(tmp_path / "work" / "EP-12/item.md", {"id": "EP-12", "kind": "epic", "status": "done", "plan": "detailed"})
    _write(tmp_path / "work" / "EP-11/T-0200-x.md", {"id": "T-0200", "kind": "task", "status": "todo"})
    msgs = [p.message for p in pm.lint(tmp_path)]
    assert not any("title が無い" in m for m in msgs)  # 付与済み・done・タスクは無指摘


def test_display_name_falls_back_title_then_heading_then_id(tmp_path: Path) -> None:
    # 表示名の導出（status と WBS 共通の 1 か所）：title→本文見出し（# <ID> 名前 から ID を除く）→素の ID。
    _write(
        tmp_path / "work" / "EP-20/item.md",
        {"id": "EP-20", "kind": "epic", "status": "done", "plan": "detailed", "title": "明示タイトル"},
        body="# EP-20 見出しの方\n",
    )
    _write(
        tmp_path / "work" / "EP-21/item.md",
        {"id": "EP-21", "kind": "epic", "status": "done", "plan": "detailed"},
        body="# EP-21 見出しからの名前\n",
    )
    _write(tmp_path / "work" / "EP-22/item.md", {"id": "EP-22", "kind": "epic", "status": "done", "plan": "detailed"})
    by_id = {n.item.id: n for n in pm.load_tree(tmp_path)[0]}
    assert pm.display_name(by_id["EP-20"]) == "明示タイトル"  # title 優先
    assert pm.display_name(by_id["EP-21"]) == "見出しからの名前"  # title 無し→H1 から ID を除く
    assert pm.display_name(by_id["EP-22"]) == "EP-22"  # title も H1 も無い→素の ID


def test_investigation_done_requires_conclusion(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # done の調査に「## 結論」が無い＝失敗（verified_by の代わりの検査）。
    d: dict[str, object] = {"id": "INV-0001", "kind": "investigation", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "INV-0001-x.md", d, body="調べた。")
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("結論" in p.message for p in errors)


def test_investigation_with_conclusion_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    d: dict[str, object] = {"id": "INV-0002", "kind": "investigation", "status": "done"}
    _write(tmp_path / "work" / "EP-01-foundation" / "INV-0002-y.md", d, body="## 結論\nこう分かった。")
    # 調査は verified_by 不要。結論があればエラーにしない。
    assert not [p for p in pm.lint(tmp_path) if p.level == "error" and "INV-0002" in p.message]


def _write_req(root: Path, req_id: str) -> None:
    """docs/requirements/ に要件ファイルを 1 つ作る（既知の要件 ID の供給源）。"""
    _write(
        root / "docs" / "requirements" / f"{req_id}.md",
        {"id": req_id, "kind": "functional", "status": "accepted"},
        body=f"# {req_id}",
    )


def test_dangling_requirement_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_req(tmp_path, "REQ-001")
    # 存在しない要件を参照＝参照エラー＝失敗（depends_on の検査と対称）。
    x: dict[str, object] = {"id": "T-0020", "kind": "task", "status": "todo", "requirements": ["REQ-9999"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0020-x.md", x)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("REQ-9999" in p.message for p in errors)


def test_existing_requirement_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_req(tmp_path, "REQ-001")
    # 実在する要件への参照はエラーにしない。
    x: dict[str, object] = {"id": "T-0021", "kind": "task", "status": "todo", "requirements": ["REQ-001"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0021-x.md", x)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_uncovered_requirement_is_info(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_req(tmp_path, "REQ-001")
    _write_req(tmp_path, "REQ-002")
    # REQ-001 だけ参照。REQ-002 はどの単位からも参照されない＝未カバーの要件（info・失敗にしない）。
    x: dict[str, object] = {"id": "T-0022", "kind": "task", "status": "todo", "requirements": ["REQ-001"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0022-x.md", x)
    problems = pm.lint(tmp_path)
    infos = [p for p in problems if p.level == "info"]
    assert any("REQ-002" in p.message and "未カバー" in p.message for p in infos)
    # 計画中は正常なので、未カバーは失敗にしない。
    assert not [p for p in problems if p.level == "error"]


def test_no_requirements_at_all_is_ok(tmp_path: Path) -> None:
    """要件を 1 つも書かない案件（docs/requirements/ 無し・requirements 参照も無し）は何も要求されない。"""
    _scaffold(tmp_path)
    x: dict[str, object] = {"id": "T-0023", "kind": "task", "status": "todo"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0023-x.md", x)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_requirements_referencing_missing_docs_is_an_error_even_without_the_dir(tmp_path: Path) -> None:
    """docs/requirements/ が無くても、非空の requirements が実在 REQ を指さなければ参照エラー（satisfies と対称の
    fail-closed）。fork で要件文書が消えても「書いたのに黙って緑」にしない。"""
    _scaffold(tmp_path)  # この scaffold は docs/requirements/ を作らない
    x: dict[str, object] = {"id": "T-0023", "kind": "task", "status": "todo", "requirements": ["REQ-001"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0023-x.md", x)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("REQ-001" in p.message and "参照エラー" in p.message for p in errors)


def _write_dem(root: Path, dem_id: str) -> None:
    """docs/demands/ に要求ファイルを 1 つ作る（既知の要求 ID の供給源）。"""
    _write(
        root / "docs" / "demands" / f"{dem_id}.md",
        {"id": dem_id, "priority": "should", "status": "received"},
        body=f"# {dem_id}",
    )


def test_req_satisfies_dangling_demand_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_dem(tmp_path, "DEM-001")
    # REQ が存在しない要求を satisfies＝上流の参照エラー＝失敗（要件→作業の参照検査と対称）。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-050.md",
        {"id": "REQ-050", "kind": "functional", "status": "accepted", "satisfies": ["DEM-999"]},
        body="# REQ-050",
    )
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("REQ-050" in p.message and "DEM-999" in p.message for p in errors)


def test_req_satisfies_existing_demand_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_dem(tmp_path, "DEM-001")
    # 実在する要求への satisfies はエラーにしない。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-051.md",
        {"id": "REQ-051", "kind": "functional", "status": "accepted", "satisfies": ["DEM-001"]},
        body="# REQ-051",
    )
    assert not any("DEM" in p.message for p in pm.lint(tmp_path) if p.level == "error")


def test_missing_demands_dir_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 要求層（docs/demands/）を持たない案件で satisfies を書かなければ何も要求されない。
    _write_req(tmp_path, "REQ-001")
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_satisfies_without_demands_dir_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 要求層が無くても、satisfies を書けば実在を要求する（fail-closed。fork で空 dir が消えても黙って緑にしない）。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-060.md",
        {"id": "REQ-060", "kind": "functional", "status": "accepted", "satisfies": ["DEM-001"]},
        body="# REQ-060",
    )
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("REQ-060" in p.message and "DEM-001" in p.message for p in errors)


def test_malformed_satisfies_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    _write_dem(tmp_path, "DEM-001")
    # スカラー文字列（配列でない）＝不正な形＝失敗（既定を不合格側に置く）。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-061.md",
        {"id": "REQ-061", "kind": "functional", "status": "accepted", "satisfies": "DEM-001"},
        body="# REQ-061",
    )
    # 配列だが DEM-<番号> の形でない要素＝失敗。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-062.md",
        {"id": "REQ-062", "kind": "functional", "status": "accepted", "satisfies": ["REQ-001"]},
        body="# REQ-062",
    )
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("REQ-061" in p.message for p in errors)
    assert any("REQ-062" in p.message and "DEM-<番号> の形でない" in p.message for p in errors)


def test_depends_on_cycle_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # A→B→A の循環。両端が実在するため既存の参照チェックでは通ってしまう。
    a: dict[str, object] = {"id": "T-0030", "kind": "task", "status": "todo", "depends_on": ["T-0031"]}
    b: dict[str, object] = {"id": "T-0031", "kind": "task", "status": "todo", "depends_on": ["T-0030"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0030-a.md", a)
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0031-b.md", b)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert any("循環" in p.message and "T-0030" in p.message and "T-0031" in p.message for p in errors)


def test_acyclic_depends_on_chain_is_ok(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # A→B→C の一直線（循環なし）はエラーにしない。
    a: dict[str, object] = {"id": "T-0040", "kind": "task", "status": "todo", "depends_on": ["T-0041"]}
    b: dict[str, object] = {"id": "T-0041", "kind": "task", "status": "todo", "depends_on": ["T-0042"]}
    c: dict[str, object] = {"id": "T-0042", "kind": "task", "status": "todo"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0040-a.md", a)
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0041-b.md", b)
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0042-c.md", c)
    assert not [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_pending_human_section_lists_blocked_and_questions(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # blocked のタスクと [要確認] を「人の判断待ち」に集約する。
    b: dict[str, object] = {"id": "T-0005", "kind": "task", "status": "blocked"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0005-b.md", b, body="本文に [要確認] を含む")
    status = pm.render_status(tmp_path)
    assert "人の判断待ち" in status
    assert "T-0005" in status
    assert "[要確認]" in status


def test_render_status_counts_leaves(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    status = pm.render_status(tmp_path)
    assert "EP-01" in status
    assert "1/2" in status  # 末端タスク done 1 / 総数 2
    assert "未分解" in status  # EP-02 は outline で子なし


def test_broken_frontmatter_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # status が不正値＝型検証で失敗。
    bad: dict[str, object] = {"id": "T-0010", "kind": "task", "status": "unknown"}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0010-bad.md", bad)
    assert [p for p in pm.lint(tmp_path) if p.level == "error"]


def test_requirement_filename_with_suffix_matches_id(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 要件ファイルは REQ-0009-<説明>.md でもよい（単位の命名規則と対称）。ID は先頭の REQ-0009。
    _write(
        tmp_path / "docs" / "requirements" / "REQ-0009-login.md",
        {"id": "REQ-0009", "kind": "functional", "status": "accepted"},
        body="# REQ-0009",
    )
    x: dict[str, object] = {"id": "T-0050", "kind": "task", "status": "todo", "requirements": ["REQ-0009"]}
    _write(tmp_path / "work" / "EP-01-foundation" / "T-0050-x.md", x)
    problems = pm.lint(tmp_path)
    # 参照は解決する（error なし）し、参照済みなので「未カバー」info も出ない。
    assert not [p for p in problems if p.level == "error" and "REQ-0009" in p.message]
    assert not [p for p in problems if "未カバー" in p.message and "REQ-0009" in p.message]


def test_deep_dependency_chain_does_not_crash(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 再帰 DFS だと Python の再帰上限(~1000)で RecursionError になる長さの一直線鎖。反復 DFS なら落ちない。
    n = 1200
    ep = tmp_path / "work" / "EP-01-foundation"
    for i in range(n):
        meta: dict[str, object] = {"id": f"T-{2000 + i}", "kind": "task", "status": "todo"}
        if i < n - 1:
            meta["depends_on"] = [f"T-{2000 + i + 1}"]  # 次へ依存（末尾だけ依存なし＝循環しない）
        _write(ep / f"T-{2000 + i}-c.md", meta)
    # 例外を投げずに検査が完了すること（循環でないので循環エラーも出ない）。
    problems = pm.lint(tmp_path)
    assert not [p for p in problems if p.level == "error" and "循環" in p.message]
