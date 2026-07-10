"""data monitor の --file-issue（監視→課題起票の閉ループ・T-0115）と --role（role フィルタ）のテスト。

JSONL は docs/serve.md の行スキーマ（契約・role を含む 9 キー）どおりに直接書く（serve は import しない＝
結合は契約だけ）。期待値はデータ構成から導出する：
- 3σ の平行移動 → psi は PSI_ALERT（0.25）を大きく超える＝大変化（test_ds_monitor と同じ導出）。
- 同一分布（別 seed）→ psi の有限標本バイアス ≈ (10-1)×(1/500+1/500) = 0.036 ≪ 0.25 ＝alert 無し。
- role フィルタ → 何行を primary / shadow で書いたか（構成）から n_served と要約の平均が決まる。
乱数は seed 明示（グローバルな種設定はしない）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from harness import issues
from harness.ds import monitor, store
from harness.ds.cli import data_app

runner = CliRunner()

# ---- 契約どおりの JSONL を作る道具（docs/serve.md の 9 キー。serve は import しない） ----


def _input_fingerprint(features: Mapping[str, Any]) -> str:
    payload = json.dumps(features, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_line(
    features: Mapping[str, Any],
    prediction: float,
    *,
    row: int = 0,
    role: str | None = "primary",
    time: str = "2026-07-06T00:00:00+00:00",
) -> str:
    """docs/serve.md の行スキーマどおりの 1 行。role=None で role キー無しの旧ログ行（T-0113 前）を作る。"""
    entry: dict[str, Any] = {
        "time": time,
        "request_id": "0" * 32,
        "row": row,
        "model": {"work": "E-0001", "name": "baseline", "version": "v1", "fingerprint": "f" * 16},
        "prediction_kind": "proba",
        "input_fingerprint": _input_fingerprint(features),
        "features": dict(features),
        "prediction": prediction,
    }
    if role is not None:
        entry["role"] = role
    return json.dumps(entry, ensure_ascii=False)


def write_log(path: Path, lines: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


BASELINE_SCHEMA = {
    "id": "fi_base",
    "description": "--file-issue / --role テストの学習基準テーブル",
    "layer": "processed",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
    ],
}


def _project_with_baseline(make_project: Callable[..., Any], n: int = 500) -> Any:  # noqa: ANN401
    proj = make_project()
    proj.add_schema(BASELINE_SCHEMA)
    df = pl.DataFrame({"id": np.arange(n), "x1": np.random.default_rng(0).normal(size=n)})
    store.save(proj.root, df, "fi_base")
    return proj


def _write_shifted_log(proj: Any, *, n: int = 500) -> None:  # noqa: ANN401
    """基準（rng(0) の標準正規）から 3σ ずらした配信ログ＝psi は 0.25 を大きく超える（大変化）。"""
    feats = [{"x1": float(v) + 3.0} for v in np.random.default_rng(1).normal(size=n)]
    write_log(
        proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "20260706.jsonl",
        [log_line(f, prediction=0.5, row=i) for i, f in enumerate(feats)],
    )


def _issue_files(root: Path) -> list[Path]:
    d = root / "issues"  # conftest の DEFAULT_CONFIG＝backend "file:issues"
    return sorted(d.glob("ISS-*.md")) if d.is_dir() else []


# ---- --file-issue（PSI_ALERT 超で冪等起票・exit 0＝門番にしない） ----


@pytest.mark.integration
def test_file_issue_idempotent_and_exit_zero(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 3σ ずらした配信ログ＝x1 の band は大変化（psi > 0.25。導出は test_ds_monitor と同じ）→ 1 件起票。
    proj = _project_with_baseline(make_project)
    _write_shifted_log(proj)
    monkeypatch.chdir(proj.root)

    first = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--file-issue"])
    assert first.exit_code == 0, f"alert があっても exit 0（門番にしない）: {first.exception!r} {first.output}"
    files = _issue_files(proj.root)
    assert len(files) == 1  # alert 列は x1 の 1 事象＝課題 1 件
    assert "起票: ISS-0001" in first.output  # 起票の成否は標準出力に 1 行

    (loaded,) = issues.load_issues(proj.root)  # 既存 API で読める＝frontmatter が契約どおり
    assert loaded.issue.id == "ISS-0001"
    assert loaded.issue.kind is issues.IssueKind.risk
    assert loaded.issue.state is issues.IssueState.open
    assert "x1" in loaded.body  # 対象列が本文に載る（決定的な内容）
    assert "監視指紋:" in loaded.body  # 冪等判定キーが本文に埋まる

    second = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--file-issue"])
    assert second.exit_code == 0
    assert len(_issue_files(proj.root)) == 1  # 同じドリフト内容の 2 回目＝増えない（冪等）
    assert "起票済み: ISS-0001" in second.output  # 既存 ID を 1 行で表示


@pytest.mark.integration
def test_resolved_same_drift_refiles(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 冪等照合は open / in-progress のみ（cli._file_drift_issue）。解決済み（resolved）の同種ドリフトが
    # 再発したら新規起票する＝「一度直したドリフトの再来」を別事象として拾う（境界の回帰）。
    proj = _project_with_baseline(make_project)
    _write_shifted_log(proj)
    monkeypatch.chdir(proj.root)

    first = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--file-issue"])
    assert first.exit_code == 0
    (iss,) = _issue_files(proj.root)  # 最初に起票される課題（open）

    # 起票済みの課題を「解決済み」に倒す（frontmatter の state を open→resolved に書き換え）。
    iss.write_text(iss.read_text(encoding="utf-8").replace("state: open", "state: resolved", 1), encoding="utf-8")
    (reloaded,) = issues.load_issues(proj.root)
    assert reloaded.issue.state is issues.IssueState.resolved  # 前提が成立していることを確かめてから再実行

    again = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--file-issue"])
    assert again.exit_code == 0
    assert len(_issue_files(proj.root)) == 2  # 同じ指紋でも resolved は照合対象外＝別の課題を新規起票
    assert "起票: ISS-0002" in again.output


@pytest.mark.unit
def test_no_alert_no_issue(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 同一分布（別 seed）：psi バイアス ≈ 9×(1/500+1/500)=0.036 ≪ 0.25 → alert 無し＝起票 0 件・exit 0。
    proj = _project_with_baseline(make_project)
    feats = [{"x1": float(v)} for v in np.random.default_rng(1).normal(size=500)]
    write_log(
        proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "20260706.jsonl",
        [log_line(f, prediction=0.5, row=i) for i, f in enumerate(feats)],
    )
    monkeypatch.chdir(proj.root)
    result = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--file-issue"])
    assert result.exit_code == 0, f"data monitor が失敗: {result.exception!r} {result.output}"
    assert _issue_files(proj.root) == []
    assert "起票" not in result.output


@pytest.mark.unit
def test_flag_off_unchanged(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # alert が出る構成でも --file-issue 無しなら issues に何も書かれない（既定 off＝後方互換）。
    proj = _project_with_baseline(make_project)
    _write_shifted_log(proj)
    monkeypatch.chdir(proj.root)
    result = runner.invoke(data_app, ["monitor", "--baseline", "fi_base"])
    assert result.exit_code == 0, f"data monitor が失敗: {result.exception!r} {result.output}"
    assert _issue_files(proj.root) == []
    assert "起票" not in result.output
    out = dict(yaml.safe_load(result.output))
    # 出力の骨格も従来どおり（余計なキーを足さない＝1 バイトも変えない方針の検査）
    assert set(out) == {"baseline", "log", "n_baseline", "n_served", "n_skipped", "psi", "prediction_summary"}
    assert {r["column"]: r["band"] for r in out["psi"]} == {"x1": "大変化"}


# ---- --role（primary | shadow | all。既定 primary＝shadow 行を除外して従来相当の集計） ----


@pytest.mark.unit
def test_read_prediction_logs_role_filter(tmp_path: Path) -> None:
    # 構成：primary 2 行＋shadow 3 行＋role 無し（旧ログ）1 行。旧ログ行は primary 扱い（後方互換）。
    lines = [
        *[log_line({"x1": float(i)}, prediction=0.5, role="primary") for i in range(2)],
        *[log_line({"x1": float(i)}, prediction=0.5, role="shadow") for i in range(3)],
        log_line({"x1": 9.0}, prediction=0.5, role=None),
    ]
    path = write_log(tmp_path / "a.jsonl", lines)
    assert monitor.read_prediction_logs([path]).n_rows == 6  # 既定 all＝従来の全行（後方互換）
    assert monitor.read_prediction_logs([path], role="all").n_rows == 6
    assert monitor.read_prediction_logs([path], role="primary").n_rows == 3  # 2＋role 無し 1
    assert monitor.read_prediction_logs([path], role="shadow").n_rows == 3
    assert monitor.read_prediction_logs([path], role="primary").n_skipped == 0  # 絞り込みは壊れ行ではない
    with pytest.raises(ValueError, match="role"):
        monitor.read_prediction_logs([path], role="oops")


@pytest.mark.integration
def test_cli_monitor_role_option(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 構成：同じ入力 5 件を primary（prediction 0.25）＋shadow（prediction 0.75）の 2 行ずつ書く（T-0113 の形）。
    # → 既定（primary）：n_served=5・要約平均 0.25。--role shadow：5・0.75。--role all：10・平均 0.5。
    proj = _project_with_baseline(make_project, n=10)
    feats = [{"x1": float(v)} for v in np.random.default_rng(1).normal(size=5)]
    lines = [log_line(f, prediction=0.25, row=i, role="primary") for i, f in enumerate(feats)]
    lines += [log_line(f, prediction=0.75, row=i, role="shadow") for i, f in enumerate(feats)]
    write_log(proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "20260706.jsonl", lines)
    monkeypatch.chdir(proj.root)

    expected = {None: (5, 0.25), "primary": (5, 0.25), "shadow": (5, 0.75), "all": (10, 0.5)}
    for role, (n, mean) in expected.items():
        args = ["monitor", "--baseline", "fi_base"] + ([] if role is None else ["--role", role])
        result = runner.invoke(data_app, args)
        assert result.exit_code == 0, f"--role {role}: {result.exception!r} {result.output}"
        out = dict(yaml.safe_load(result.output))
        assert out["n_served"] == n  # 既定 primary＝shadow 行を二重計上しない
        (summary,) = out["prediction_summary"]
        assert summary["mean"] == pytest.approx(mean)  # 対象 role の行だけの要約

    bad = runner.invoke(data_app, ["monitor", "--baseline", "fi_base", "--role", "oops"])
    assert bad.exit_code != 0  # 不正な role は usage error（黙って全件にしない）
