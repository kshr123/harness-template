"""data score の CLI 契約（門番にしない＝exit 0・--file-issue の冪等起票・空ログでも落ちない）のテスト。

答え合わせの中身（指標・join・band）は test_ds_scoring.py が担う。ここは CLI の入口の契約を固める
（drift の test_monitor_file_issue.py と同型）。JSONL は docs/serve.md の行スキーマどおりに直接書く
（serve は import しない＝結合は契約だけ）。期待値はデータ構成から導く：
- 予測ラベル [1,1,0,0] に実績 [0,0,1,1]＝全問外れ＝accuracy 0.0。約束 1.0 に対し相対劣化 1.0＝大変化→起票。
- 空ログ＝突き合わせ 0＝門番にしないので exit 0（例外で定期実行を落とさない）。
乱数は使わない（決定的に構成する）。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from typer.testing import CliRunner

from harness import issues
from harness.ds import data
from harness.ds import models as model_store
from harness.ds.cli import data_app
from harness.ds.features import Columns, FeaturePipeline

pytestmark = pytest.mark.integration
runner = CliRunner()


def _make_champion(proj: Any, *, metrics: Mapping[str, float]) -> Any:  # noqa: ANN401
    """champion 1 版を作る（昇格時 metrics＝約束の値）。モデル自体は答え合わせに使わない（版と約束だけ引く）。"""
    df = data.generate_synthetic(n=40, seed=0)
    y = df["y"].to_numpy().astype(np.float64)
    est = Pipeline(
        [
            ("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    est.fit(df, y)
    record = model_store.save_model(proj.root, est, name="baseline", work="E-0001", metrics=dict(metrics))
    model_store.promote_model(
        proj.root,
        work="E-0001",
        name="baseline",
        version=record.version,
        thresholds={"accuracy": 0.5},
        primary="accuracy",
    )
    return record


def _log_line(fp: str, prediction: float, *, version: str, time: str = "2026-07-06T00:00:00+00:00") -> str:
    entry: dict[str, Any] = {
        "time": time,
        "request_id": "0" * 32,
        "row": 0,
        "model": {"work": "E-0001", "name": "baseline", "version": version, "fingerprint": "f" * 16},
        "prediction_kind": "proba",
        "input_fingerprint": fp,
        "features": {"x1": 0.0, "x2": 0.0},
        "prediction": prediction,
        "role": "primary",
    }
    return json.dumps(entry, ensure_ascii=False)


def _write_logs(proj: Any, lines: Sequence[str]) -> None:  # noqa: ANN401
    path = proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "20260706.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_actuals(proj: Any, fps: Sequence[str], ys: Sequence[int]) -> None:  # noqa: ANN401
    pl.DataFrame({"input_fingerprint": list(fps), "y": list(ys)}).write_parquet(proj.root / "actuals.parquet")


def _proba_logs(version: str) -> list[str]:
    """予測ラベル [1,1,0,0]（proba 0.9/0.9/0.1/0.1・閾値 0.5）を指紋 a..d で書いた行。"""
    return [_log_line(fp, p, version=version) for fp, p in zip("abcd", [0.9, 0.9, 0.1, 0.1], strict=True)]


def _issue_files(root: Path) -> list[Path]:
    d = root / "issues"  # conftest の DEFAULT_CONFIG＝backend "file:issues"
    return sorted(d.glob("ISS-*.md")) if d.is_dir() else []


_SCORE_ARGS = ["score", "--model", "E-0001/baseline", "--actuals", "actuals.parquet", "--actual-column", "y"]


def test_degradation_files_issue_idempotent_and_exit_zero(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 予測ラベル [1,1,0,0]（proba 0.9/0.9/0.1/0.1）に実績 [0,0,1,1]＝accuracy 0.0。約束 1.0→相対劣化 1.0＝大変化。
    proj = make_project()
    record = _make_champion(proj, metrics={"accuracy": 1.0})
    _write_logs(proj, _proba_logs(record.version))
    _write_actuals(proj, list("abcd"), [0, 0, 1, 1])
    monkeypatch.chdir(proj.root)

    first = runner.invoke(data_app, [*_SCORE_ARGS, "--file-issue"])
    assert first.exit_code == 0, f"大変化でも exit 0（門番にしない）: {first.exception!r} {first.output}"
    files = _issue_files(proj.root)
    assert len(files) == 1  # accuracy の大変化＝課題 1 件
    assert "起票: ISS-0001" in first.output

    (loaded,) = issues.load_issues(proj.root)
    assert loaded.issue.kind is issues.IssueKind.risk
    assert loaded.issue.state is issues.IssueState.open
    assert "accuracy" in loaded.body  # 劣化した指標が本文に載る
    assert "答え合わせ指紋:" in loaded.body  # 冪等判定キー

    second = runner.invoke(data_app, [*_SCORE_ARGS, "--file-issue"])
    assert second.exit_code == 0
    assert len(_issue_files(proj.root)) == 1  # 同じ劣化事象の 2 回目＝増えない（冪等）
    assert "起票済み: ISS-0001" in second.output


def test_stable_does_not_file_issue(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 予測ラベル [1,1,0,0] に実績 [1,1,0,0]＝accuracy 1.0＝約束どおり＝大変化なし＝起票しない（exit 0）。
    proj = make_project()
    record = _make_champion(proj, metrics={"accuracy": 1.0})
    _write_logs(proj, _proba_logs(record.version))
    _write_actuals(proj, list("abcd"), [1, 1, 0, 0])
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, [*_SCORE_ARGS, "--file-issue"])
    assert result.exit_code == 0
    assert _issue_files(proj.root) == []  # 劣化なし＝起票なし


def test_empty_logs_exit_zero_no_issue(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # 予測ログ 0 行（昇格直後・まだ流入なし）＝門番にしない：exit 0・起票なし（例外で定期実行を落とさない＝H1）。
    proj = make_project()
    _make_champion(proj, metrics={"accuracy": 1.0})
    _write_logs(proj, [])  # 空
    _write_actuals(proj, list("abcd"), [0, 0, 1, 1])
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, [*_SCORE_ARGS, "--file-issue"])
    assert result.exit_code == 0, f"空ログでも exit 0: {result.exception!r} {result.output}"
    assert _issue_files(proj.root) == []


def test_missing_champion_exits_nonzero(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # champion が無いのは唯一の非 0（黙って空で測らない）。
    proj = make_project()
    _write_actuals(proj, list("abcd"), [0, 0, 1, 1])
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, _SCORE_ARGS)
    assert result.exit_code != 0
    assert "champion が無い" in result.output
