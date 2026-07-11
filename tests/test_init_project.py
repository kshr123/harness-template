"""init-project（複製後の初期化）の検査。

期待値は入力（tmp_path に組み立てた案件ツリー）の構成から導く（ハードコード期待値を書かない）。
本体領域には触れない・案件領域だけ白紙化する・べき等・fork していない状態では拒否する、を固定する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from harness import init_project

pytestmark = pytest.mark.unit


def _make_project(root: Path, *, profiles: str = 'profiles = ["harness.ds", "harness.serve"]') -> None:
    """案件領域＋本体領域の最小ツリーを tmp_path に作る。"""
    # 案件領域（消える／雛形に戻るべきもの）
    (root / "work" / "EP-99-old").mkdir(parents=True)
    (root / "work" / "EP-99-old" / "item.md").write_text("---\nid: EP-99\nkind: epic\n---\n前案件\n", encoding="utf-8")
    (root / "work" / "T-9001-loose.md").write_text("---\nid: T-9001\nkind: task\n---\n前案件\n", encoding="utf-8")
    (root / "issues").mkdir()
    (root / "issues" / "ISS-0099-old.md").write_text("---\nid: ISS-0099\n---\n前案件の課題\n", encoding="utf-8")
    (root / "docs" / "requirements").mkdir(parents=True)
    (root / "docs" / "requirements" / "REQ-005.md").write_text(
        "---\nid: REQ-005\n---\n前案件の要件\n", encoding="utf-8"
    )
    (root / "docs" / "charter.md").write_text("# 前案件の憲章\n重要な前案件固有の記述\n", encoding="utf-8")
    (root / "docs" / "learnings.md").write_text("# learnings\n## L-999 前案件の気づき\n", encoding="utf-8")
    (root / "docs" / "structure-review-2099.md").write_text("履歴\n", encoding="utf-8")
    (root / "data" / "raw").mkdir(parents=True)
    (root / "data" / "raw" / "big.parquet").write_bytes(b"\x00\x01\x02")
    # 本体領域（触れてはいけないもの）
    (root / "src" / "harness").mkdir(parents=True)
    (root / "src" / "harness" / "checks.py").write_text("# 本体\n", encoding="utf-8")
    (root / ".claude" / "skills" / "harvest").mkdir(parents=True)
    (root / ".claude" / "skills" / "harvest" / "SKILL.md").write_text("# harvest\n", encoding="utf-8")
    (root / ".harness").mkdir()
    (root / ".harness" / "config.toml").write_text("# コメント\n" + profiles + "\n\n[data]\n", encoding="utf-8")


def test_scrub_empties_project_area_and_keeps_core(tmp_path: Path) -> None:
    _make_project(tmp_path)
    init_project.scrub(tmp_path, [])

    # 案件領域は消える／雛形に戻る
    assert list((tmp_path / "work").glob("EP-*")) == []
    assert list((tmp_path / "work").glob("T-*")) == []
    assert list((tmp_path / "issues").glob("ISS-*")) == []
    assert list((tmp_path / "docs" / "requirements").glob("REQ-005*")) == []
    assert (tmp_path / "docs" / "requirements" / "REQ-001.md").is_file()  # 雛形が置かれる
    assert "前案件" not in (tmp_path / "docs" / "charter.md").read_text(encoding="utf-8")
    assert "L-999" not in (tmp_path / "docs" / "learnings.md").read_text(encoding="utf-8")
    assert list((tmp_path / "docs").glob("structure-review-*.md")) == []
    assert not (tmp_path / "data").exists()  # 生成物は消える

    # 本体領域は不変
    assert (tmp_path / "src" / "harness" / "checks.py").read_text(encoding="utf-8") == "# 本体\n"
    assert (tmp_path / ".claude" / "skills" / "harvest" / "SKILL.md").read_text(encoding="utf-8") == "# harvest\n"


def test_scrub_sets_profiles_and_preserves_comments(tmp_path: Path) -> None:
    _make_project(tmp_path)
    init_project.scrub(tmp_path, ["harness.ds"])
    cfg = (tmp_path / ".harness" / "config.toml").read_text(encoding="utf-8")
    assert 'profiles = ["harness.ds"]' in cfg
    assert "harness.serve" not in cfg  # 前の値は残らない
    assert "# コメント" in cfg  # 他の行（コメント・[data]）は保つ
    assert "[data]" in cfg


def test_scrub_empty_profiles_writes_empty_list(tmp_path: Path) -> None:
    _make_project(tmp_path)
    init_project.scrub(tmp_path, [])
    cfg = (tmp_path / ".harness" / "config.toml").read_text(encoding="utf-8")
    assert "profiles = []" in cfg


def test_scrub_is_idempotent(tmp_path: Path) -> None:
    _make_project(tmp_path)
    init_project.scrub(tmp_path, [])
    # 2 回目も例外を出さず、同じ最終状態になる（雛形は雛形のまま・案件領域は空のまま）
    second = init_project.scrub(tmp_path, [])
    assert (tmp_path / "docs" / "requirements" / "REQ-001.md").is_file()
    assert list((tmp_path / "work").glob("EP-*")) == []
    assert "profiles = []" in (tmp_path / ".harness" / "config.toml").read_text(encoding="utf-8")
    # 雛形化は 2 回目も行う（べき等＝戻す）。消去対象は 2 回目には無い（構造的に空）。
    assert not any(rel.startswith("work/EP-") for rel in second.removed)


def test_is_forked_requires_upstream_remote() -> None:
    assert init_project.is_forked({"origin", "upstream"}) is True
    assert init_project.is_forked({"origin"}) is False  # まだ fork 設定前＝本体扱い
    assert init_project.is_forked(set()) is False


def test_blocking_reason_refuses_before_fork_and_allows_after() -> None:
    reason = init_project.blocking_reason(forked=False)
    assert reason is not None
    assert "upstream" in reason  # 理由が何を確認しているかを名指しする
    assert init_project.blocking_reason(forked=True) is None


def test_set_profiles_appends_when_line_absent(tmp_path: Path) -> None:
    cfg = tmp_path / ".harness" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[data]\ndefault_backend = "local"\n', encoding="utf-8")
    init_project.set_profiles(tmp_path, ["harness.ops"])
    text = cfg.read_text(encoding="utf-8")
    assert 'profiles = ["harness.ops"]' in text
    assert "[data]" in text  # 既存の設定は消えない


# --- CLI 経路（typer 配線＋安全装置）。git 呼び出し・verify は monkeypatch で差し込む ---

runner = CliRunner()


def _invoke_init(
    monkeypatch: pytest.MonkeyPatch, root: Path, remotes: set[str], args: list[str], stdin: str | None = None
) -> Any:
    import typer

    from harness import checks, cli
    from harness import init_project as ip

    # cli は `from harness import checks, init_project` で同じモジュール実体を参照するので、実体側を差し替える。
    monkeypatch.setattr(ip, "list_remotes", lambda _root: remotes)
    monkeypatch.setattr(checks, "run_check", lambda _root, _level: 0)  # verify は e2e/CI が実測
    monkeypatch.chdir(root)
    app = typer.Typer()
    app.command()(cli.init_project_cmd)  # console_script の本体をそのまま CliRunner に載せる
    return runner.invoke(app, args, input=stdin)


def test_cli_refuses_before_fork_and_deletes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _make_project(tmp_path)
    result = _invoke_init(monkeypatch, tmp_path, {"origin"}, ["--force"])
    assert result.exit_code == 1, result.output
    assert "upstream" in result.output
    # 拒否したので案件領域は残っている（誤爆で本体/案件を消さない）
    assert (tmp_path / "work" / "EP-99-old" / "item.md").is_file()
    assert (tmp_path / "issues" / "ISS-0099-old.md").is_file()


def test_cli_scrubs_when_forked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _make_project(tmp_path)
    result = _invoke_init(monkeypatch, tmp_path, {"origin", "upstream"}, ["--force", "--profiles", ""])
    assert result.exit_code == 0, result.output
    assert list((tmp_path / "work").glob("EP-*")) == []
    assert "profiles = []" in (tmp_path / ".harness" / "config.toml").read_text(encoding="utf-8")


def test_cli_aborts_without_force_when_declined(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # --force を付けず、確認プロンプトに「n」で答えると中止し、何も消さない（対話の安全装置）。
    _make_project(tmp_path)
    result = _invoke_init(monkeypatch, tmp_path, {"origin", "upstream"}, [], stdin="n\n")
    assert result.exit_code != 0
    assert (tmp_path / "work" / "EP-99-old" / "item.md").is_file()  # 中止したので残る
