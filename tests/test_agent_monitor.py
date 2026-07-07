"""agent monitor（エージェント実行ログの監視）のテスト。

JSONL は docs/agent.md の行スキーマ（AGENT_LOG_FIELDS の契約）どおりに**直接書く**（runtime は起動しない・
build_log_row も呼ばない＝結合は契約だけ、という設計をテストの形でも守る。test_ds_monitor と同じ作法）。
期待値はすべて構成から導出する：率＝混ぜた stop_reason の比・分位＝ニアレストランク法を既知の数列に当てた
値（n=10 なら p05→1 番目・p25→3 番目・p50→5 番目・p75→8 番目・p95→10 番目）・頻度＝並べたツール名の数。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from harness import issues
from harness.agent import monitor
from harness.agent.cli import agent_app

runner = CliRunner()

# ---- 契約どおりの JSONL を作る道具（AGENT_LOG_FIELDS の 10 キー。runtime は import しない） ----


def row_dict(
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
    turns: int = 1,
    tools_used: Sequence[str] = (),
    time: str = "2026-07-06T00:00:00+00:00",
) -> dict[str, Any]:
    """docs/agent.md の行スキーマどおりの 1 行（キー 10 個すべて・値の型も契約どおり）。"""
    return {
        "time": time,
        "request_id": "0" * 32,
        "agent": {"name": "helper", "provider": "dummy", "model": "dummy-model", "prompt_fingerprint": "f" * 64},
        "input_fingerprint": "a" * 64,
        "input": "ping",
        "output": "pong",
        "stop_reason": stop_reason,
        "turns": turns,
        "tools_used": list(tools_used),
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def write_log(path: Path, lines: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---- band（率の目安 0.05 / 0.2。門番でない＝表示の離散化） ----


@pytest.mark.unit
def test_rate_band_thresholds() -> None:
    assert monitor.rate_band(0.0) == "安定"
    assert monitor.rate_band(0.049) == "安定"
    assert monitor.rate_band(0.05) == "要注意"  # 境界は上のバンドへ（psi_band と同じ規約）
    assert monitor.rate_band(0.19) == "要注意"
    assert monitor.rate_band(0.2) == "大変化"


# ---- monitor（率・分位・ツール頻度＝構成から導出。verified_by の正本テスト） ----


@pytest.mark.unit
def test_monitor_rates_and_cost_from_constructed_logs() -> None:
    # 10 行：end_turn 7・max_turns 2・refusal 1 → non_end_turn_rate = 3/10、max_turns_rate = 2/10。
    # input_tokens = 10..100（10 刻み）・output_tokens = 5..50（5 刻み）・turns = 1..10。
    # ニアレストランク（n=10）：p05→1 番目・p25→3 番目・p50→5 番目・p75→8 番目・p95→10 番目の値。
    stops = ["end_turn"] * 7 + ["max_turns"] * 2 + ["refusal"]
    tools: list[tuple[str, ...]] = [("calculator", "calculator", "search"), ("calculator",)] + [()] * 8
    rows = tuple(
        monitor.AgentLogRow(
            stop_reason=stop,
            input_tokens=10 * (i + 1),
            output_tokens=5 * (i + 1),
            turns=i + 1,
            tools_used=tools[i],
        )
        for i, stop in enumerate(stops)
    )
    report = monitor.monitor(monitor.AgentLogs(rows=rows, n_skipped=0))

    assert report.n_rows == 10 and report.n_skipped == 0
    assert report.stop_reason == {"end_turn": 7, "max_turns": 2, "refusal": 1}
    assert report.non_end_turn_rate == pytest.approx(0.3)  # 1 − 7/10
    assert report.max_turns_rate == pytest.approx(0.2)  # 2/10
    assert report.cost["input_tokens"] == {"p05": 10.0, "p25": 30.0, "p50": 50.0, "p75": 80.0, "p95": 100.0}
    assert report.cost["output_tokens"] == {"p05": 5.0, "p25": 15.0, "p50": 25.0, "p75": 40.0, "p95": 50.0}
    assert report.cost["turns"] == {"p05": 1.0, "p25": 3.0, "p50": 5.0, "p75": 8.0, "p95": 10.0}
    assert report.tools_used == {"calculator": 3, "search": 1}  # 並べた回数どおり（呼んだ回数）

    out = report.to_dict()
    assert list(out) == [  # YAML の骨格（挿入順）＝CLI が safe_dump(sort_keys=False) で出す並び
        "n_rows",
        "n_skipped",
        "stop_reason",
        "non_end_turn_rate",
        "non_end_turn_band",
        "max_turns_rate",
        "cost",
        "tools_used",
    ]
    assert out["non_end_turn_band"] == "大変化"  # 0.3 >= 0.2


@pytest.mark.unit
def test_monitor_zero_and_single_row_degrade_gracefully() -> None:
    # 0 行：率は 0.0（0 割を作らない）・分位は空 dict（数字を捏造しない）。
    empty = monitor.monitor(monitor.AgentLogs(rows=(), n_skipped=0))
    assert empty.n_rows == 0
    assert empty.non_end_turn_rate == 0.0 and empty.max_turns_rate == 0.0
    assert empty.cost == {"input_tokens": {}, "output_tokens": {}, "turns": {}}
    assert empty.tools_used == {}
    # 1 行：ニアレストランクは全分位ともその値（max_turns 1 行 → 率はどちらも 1.0）。
    row = monitor.AgentLogRow(stop_reason="max_turns", input_tokens=7, output_tokens=3, turns=2, tools_used=())
    single = monitor.monitor(monitor.AgentLogs(rows=(row,), n_skipped=0))
    assert single.non_end_turn_rate == pytest.approx(1.0)
    assert single.max_turns_rate == pytest.approx(1.0)
    assert single.cost["input_tokens"] == {"p05": 7.0, "p25": 7.0, "p50": 7.0, "p75": 7.0, "p95": 7.0}


# ---- read_agent_logs（契約どおりの行を読む・壊れ行は警告して読み飛ばす・--since 境界） ----


@pytest.mark.unit
def test_read_agent_logs_parses_contract_rows(tmp_path: Path) -> None:
    lines = [
        json.dumps(row_dict(stop_reason="end_turn", input_tokens=10, output_tokens=5, turns=1)),
        json.dumps(
            row_dict(stop_reason="max_turns", input_tokens=20, output_tokens=15, turns=8, tools_used=["calculator"])
        ),
    ]
    logs = monitor.read_agent_logs([write_log(tmp_path / "a.jsonl", lines)])
    assert logs.n_rows == 2 and logs.n_skipped == 0
    assert logs.rows[0] == monitor.AgentLogRow("end_turn", 10, 5, 1, ())
    assert logs.rows[1] == monitor.AgentLogRow("max_turns", 20, 15, 8, ("calculator",))


@pytest.mark.unit
def test_read_agent_logs_skips_broken_rows_with_warning(tmp_path: Path) -> None:
    good = [json.dumps(row_dict(input_tokens=1)), json.dumps(row_dict(input_tokens=2))]
    no_usage = row_dict()
    del no_usage["usage"]  # 消費キーの欠け
    str_tokens = row_dict()
    str_tokens["usage"] = {"input_tokens": "10", "output_tokens": 5}  # 型違い（str）
    bad_tools = row_dict()
    bad_tools["tools_used"] = "calculator"  # list[str] でない
    broken = ["{oops", json.dumps(no_usage), json.dumps(str_tokens), json.dumps(bad_tools)]
    path = write_log(tmp_path / "a.jsonl", [good[0], *broken, "", good[1]])  # 空行は数えない
    with pytest.warns(UserWarning, match="壊れ行 4 行"):
        logs = monitor.read_agent_logs([path])
    assert logs.n_rows == 2  # 壊れ行があっても読める行は生きる（監視が盲目になるより縮退）
    assert logs.n_skipped == 4
    assert [r.input_tokens for r in logs.rows] == [1, 2]


@pytest.mark.unit
def test_read_agent_logs_since_includes_boundary_date(tmp_path: Path) -> None:
    path = write_log(
        tmp_path / "a.jsonl",
        [
            json.dumps(row_dict(input_tokens=1, time="2026-07-01T12:00:00+00:00")),
            json.dumps(row_dict(input_tokens=2, time="2026-07-06T00:00:00+00:00")),
        ],
    )
    assert monitor.read_agent_logs([path]).n_rows == 2
    since = monitor.read_agent_logs([path], since=date(2026, 7, 3))
    assert since.n_rows == 1  # 7/1 の行が落ちる
    assert since.n_skipped == 0  # 日付の絞り込みは壊れ行ではない
    assert since.rows[0].input_tokens == 2
    # 境界日は含む（YYYY-MM-DD 以降＝その日を含む）
    assert monitor.read_agent_logs([path], since=date(2026, 7, 6)).n_rows == 1


@pytest.mark.unit
def test_read_agent_logs_empty_input(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert monitor.read_agent_logs([empty]).n_rows == 0
    assert monitor.read_agent_logs([]).n_rows == 0  # ファイル無しも同じ縮退


# ---- CLI（agent monitor＝YAML・exit 0・既定 glob・--file-issue の冪等） ----


def _write_runs(root: Path, lines: Sequence[str]) -> Path:
    return write_log(root / "artifacts" / "agent" / "runs" / "helper" / "20260706.jsonl", lines)


@pytest.mark.integration
def test_cli_agent_monitor_yaml_via_default_glob(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # end_turn 1 行＋max_turns 1 行 → non_end_turn_rate = 0.5（大変化）・max_turns_rate = 0.5。
    proj = make_project()
    _write_runs(
        proj.root,
        [
            json.dumps(row_dict(stop_reason="end_turn", tools_used=["calculator"])),
            json.dumps(row_dict(stop_reason="max_turns")),
        ],
    )
    monkeypatch.chdir(proj.root)
    result = runner.invoke(agent_app, ["monitor"])
    assert result.exit_code == 0, f"agent monitor が失敗: exc={result.exception!r} {result.output}"
    out = dict(yaml.safe_load(result.output))
    assert out["log"] == "artifacts/agent/runs/**/*.jsonl"  # 既定 glob で拾えている
    assert out["n_rows"] == 2 and out["n_skipped"] == 0
    assert out["stop_reason"] == {"end_turn": 1, "max_turns": 1}
    assert out["non_end_turn_rate"] == pytest.approx(0.5)
    assert out["non_end_turn_band"] == "大変化"  # 0.5 >= 0.2（表示の目安。exit code は 0 のまま＝門番でない）
    assert out["max_turns_rate"] == pytest.approx(0.5)
    assert out["tools_used"] == {"calculator": 1}
    assert set(out["cost"]) == {"input_tokens", "output_tokens", "turns"}

    bad = runner.invoke(agent_app, ["monitor", "--since", "07/03/2026"])
    assert bad.exit_code != 0  # 日付の書式違いは usage error（黙って全件にしない。判定でなく引数の検査）


@pytest.mark.integration
def test_cli_agent_monitor_file_issue_is_idempotent(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 全行 max_turns → 帯は大変化 → 起票。二度叩いても open 課題は 1 件（決定的タイトルの再起票をしない）。
    proj = make_project()
    _write_runs(proj.root, [json.dumps(row_dict(stop_reason="max_turns"))])
    monkeypatch.chdir(proj.root)

    first = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert first.exit_code == 0, f"1 回目が失敗: exc={first.exception!r} {first.output}"
    second = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert second.exit_code == 0, f"2 回目が失敗: exc={second.exception!r} {second.output}"

    loaded = issues.load_issues(proj.root)
    assert len(loaded) == 1  # 冪等＝2 連続で 1 件だけ
    issue = loaded[0].issue
    assert issue.state is issues.IssueState.open
    assert issue.title == "[agent-monitor] non_end_turn_rate 大変化"  # 決定的タイトル（冪等の鍵）
    assert issue.id in second.output  # 2 回目は既存 ID を案内する


@pytest.mark.integration
def test_cli_agent_monitor_file_issue_refiles_after_resolved(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 冪等照合は open / in-progress のみ（_agent_monitor の state is open フィルタ）。resolved に倒した
    # 同種ドリフト（同タイトル）の再来は新規起票する＝後半円の goal 未達検知（T-0098・test_ds_monitor の
    # test_resolved_same_drift_refiles と同じ境界をここでも守る）。
    proj = make_project()
    _write_runs(proj.root, [json.dumps(row_dict(stop_reason="max_turns"))])
    monkeypatch.chdir(proj.root)

    first = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert first.exit_code == 0, f"1 回目が失敗: exc={first.exception!r} {first.output}"
    (loaded,) = issues.load_issues(proj.root)
    assert loaded.issue.state is issues.IssueState.open

    # frontmatter の state を open→resolved に書き換える（人が対処済みにした想定）。
    path = loaded.path
    path.write_text(path.read_text(encoding="utf-8").replace("state: open", "state: resolved", 1), encoding="utf-8")
    (reloaded,) = issues.load_issues(proj.root)
    assert reloaded.issue.state is issues.IssueState.resolved  # 前提が成立してから再実行する

    again = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert again.exit_code == 0, f"2 回目が失敗: exc={again.exception!r} {again.output}"
    loaded_all = issues.load_issues(proj.root)
    assert len(loaded_all) == 2  # 同じ指紋でも resolved は照合対象外＝新規に 1 件起票
    titles = {li.issue.title for li in loaded_all}
    assert titles == {"[agent-monitor] non_end_turn_rate 大変化"}  # 両方とも同じ決定的タイトル


@pytest.mark.integration
def test_filed_issue_has_exit_condition_section(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 起票 body に退場条件（goal）節が入る（T-0098＝人が triage で読む固定文。機械はこの節を読まない・
    # 検査は issues.run_checks の resolved⟺done 不変条件と monitor の再起票が担う）。
    proj = make_project()
    _write_runs(proj.root, [json.dumps(row_dict(stop_reason="max_turns"))])
    monkeypatch.chdir(proj.root)

    result = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert result.exit_code == 0, f"起票が失敗: exc={result.exception!r} {result.output}"

    (loaded,) = issues.load_issues(proj.root)
    assert "## 退場条件（goal）" in loaded.body  # 節見出しが入る
    assert "done" in loaded.body  # 条件 (i)：promoted_to タスクが done
    assert "再起票" in loaded.body  # 条件 (ii)：次回 monitor で帯が安定＝再起票されない


@pytest.mark.integration
def test_cli_agent_monitor_file_issue_skips_stable_band(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 全行 end_turn → non_end_turn_rate = 0.0（安定）→ 起票しない。ログ 0 行（glob 空振り）でも exit 0。
    proj = make_project()
    _write_runs(proj.root, [json.dumps(row_dict(stop_reason="end_turn"))])
    monkeypatch.chdir(proj.root)
    result = runner.invoke(agent_app, ["monitor", "--file-issue"])
    assert result.exit_code == 0
    assert issues.load_issues(proj.root) == []  # 安定の帯では起票しない

    empty = make_project()
    monkeypatch.chdir(empty.root)
    result = runner.invoke(agent_app, ["monitor"])
    assert result.exit_code == 0, f"空ログで非 0: exc={result.exception!r} {result.output}"
    assert dict(yaml.safe_load(result.output))["n_rows"] == 0  # 門番にしない＝縮退して exit 0
