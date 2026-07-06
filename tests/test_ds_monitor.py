"""data monitor（配信ログ×学習基準の分布監視）のテスト。

JSONL は docs/serve.md の行スキーマ（契約）どおりに**直接書く**（serve は起動しない・import しない＝
結合は契約だけ、という設計をテストの形でも守る）。期待値はデータ構成から導出する：
- 同一分布 → psi≈0（有限標本のバイアスは概ね (ビン数-1)×(1/n_基準+1/n_配信)＝ここの構成では 0.1 に遠く届かない）
- 平行移動（3σ）→ 配信の質量の大半が基準の外側ビンへ寄る＝psi は 0.25 を大きく超える
- drift_auc は見分けられなければ 0.5 近傍・分離すれば 1.0 近傍（test_ds_eda_integration と同じ導出）。
乱数は seed 明示（グローバルな種設定はしない）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from harness.ds import monitor, store
from harness.ds.cli import data_app

runner = CliRunner()

# ---- 契約どおりの JSONL を作る道具（docs/serve.md の 8 キー。serve は import しない） ----


def _input_fingerprint(features: Mapping[str, Any]) -> str:
    """features の正準 JSON（キー昇順・区切り最小）の sha256（docs/serve.md の定義どおり再計算）。"""
    payload = json.dumps(features, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_line(
    features: Mapping[str, Any],
    prediction: float | list[float],
    *,
    row: int = 0,
    kind: str = "proba",
    time: str = "2026-07-06T00:00:00+00:00",
) -> str:
    """docs/serve.md の行スキーマどおりの 1 行（キー 8 個すべて・値の型も契約どおり）。"""
    return json.dumps(
        {
            "time": time,
            "request_id": "0" * 32,
            "row": row,
            "model": {"work": "E-0001", "name": "baseline", "version": "v1", "fingerprint": "f" * 16},
            "prediction_kind": kind,
            "input_fingerprint": _input_fingerprint(features),
            "features": dict(features),
            "prediction": prediction,
        },
        ensure_ascii=False,
    )


def write_log(path: Path, lines: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def served_from(features: pl.DataFrame, *, kind: str = "proba", prediction: float = 0.5) -> monitor.ServedLog:
    """unit テスト用：unnest 済み features から ServedLog を直接組む（読み込みは別テストで検証）。"""
    n = features.height
    return monitor.ServedLog(features=features, prediction_kinds=[kind] * n, predictions=[prediction] * n, n_skipped=0)


# ---- band（psi の目安 0.1 / 0.25。eda.psi の docstring と同じ閾値） ----


@pytest.mark.unit
def test_psi_band_thresholds() -> None:
    assert monitor.psi_band(0.0) == "安定"
    assert monitor.psi_band(0.099) == "安定"
    assert monitor.psi_band(0.1) == "要注意"  # 0.1〜0.25 = 要注意（境界は上のバンドへ）
    assert monitor.psi_band(0.249) == "要注意"
    assert monitor.psi_band(0.25) == "大変化"  # 0.25 以上 = 大変化


# ---- read_prediction_logs（契約どおりの行を読む・壊れ行は警告して読み飛ばす） ----


@pytest.mark.unit
def test_read_prediction_logs_parses_contract_rows(tmp_path: Path) -> None:
    rows = [{"x1": float(i), "cat": "a"} for i in range(3)]
    path = write_log(tmp_path / "a.jsonl", [log_line(f, prediction=0.5, row=i) for i, f in enumerate(rows)])
    served = monitor.read_prediction_logs([path])
    assert served.n_rows == 3
    assert served.n_skipped == 0
    assert set(served.features.columns) == {"x1", "cat"}  # features struct の unnest
    assert served.features["x1"].to_list() == [0.0, 1.0, 2.0]
    assert served.prediction_kinds == ["proba"] * 3
    assert served.predictions == [0.5] * 3


@pytest.mark.unit
def test_read_prediction_logs_skips_broken_lines_with_warning(tmp_path: Path) -> None:
    good = [log_line({"x1": 1.0}, prediction=0.5), log_line({"x1": 2.0}, prediction=0.7)]
    broken = [
        "{oops",  # JSON として読めない
        json.dumps([1, 2]),  # dict でない
        json.dumps({"time": "2026-07-06T00:00:00+00:00", "prediction": 0.5}),  # features が無い
        log_line({"x2": 9.9}, prediction=0.5),  # features のキー集合が先頭行と不一致
        log_line({"x1": 3.0}, prediction=0.5, kind="multiclass_proba"),  # kind と prediction の形が食い違う
    ]
    path = write_log(tmp_path / "a.jsonl", [good[0], *broken, "", good[1]])  # 空行は数えない
    with pytest.warns(UserWarning, match="壊れ行 5 行"):
        served = monitor.read_prediction_logs([path])
    assert served.n_rows == 2  # 壊れ行があっても読める行は生かす（監視が盲目になるより縮退）
    assert served.n_skipped == 5
    assert served.features["x1"].to_list() == [1.0, 2.0]  # 読めた 2 行＝good[0]/good[1]（壊れ 5 行は全て除外）


@pytest.mark.unit
def test_read_prediction_logs_since_filters_by_date(tmp_path: Path) -> None:
    path = write_log(
        tmp_path / "a.jsonl",
        [
            log_line({"x1": 1.0}, prediction=0.5, time="2026-07-01T12:00:00+00:00"),
            log_line({"x1": 2.0}, prediction=0.5, time="2026-07-06T00:00:00+00:00"),
        ],
    )
    assert monitor.read_prediction_logs([path]).n_rows == 2
    since = monitor.read_prediction_logs([path], since=date(2026, 7, 3))
    assert since.n_rows == 1  # 7/1 の行が落ちる
    assert since.n_skipped == 0  # 日付の絞り込みは壊れ行ではない
    assert since.features["x1"].to_list() == [2.0]
    # 境界日は含む（YYYY-MM-DD 以降＝その日を含む）
    assert monitor.read_prediction_logs([path], since=date(2026, 7, 6)).n_rows == 1


@pytest.mark.unit
def test_read_prediction_logs_empty_input(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    served = monitor.read_prediction_logs([empty])
    assert served.n_rows == 0 and served.n_skipped == 0
    assert monitor.read_prediction_logs([]).n_rows == 0  # ファイル無しも同じ縮退


# ---- monitor（psi/band・列の選択・型不一致の縮退・予測の要約） ----


@pytest.mark.unit
def test_monitor_same_distribution_is_stable() -> None:
    # 同一分布（別 seed）：psi の有限標本バイアス ≈ (10-1)×(1/500+1/500) = 0.036 ≪ 0.1 → 安定。
    baseline = pl.DataFrame({"x1": np.random.default_rng(0).normal(size=500)})
    served = served_from(pl.DataFrame({"x1": np.random.default_rng(1).normal(size=500)}))
    report = monitor.monitor(baseline, served)
    assert report.n_baseline == 500 and report.n_served == 500
    row = report.psi.to_dicts()[0]
    assert row["column"] == "x1"
    assert row["psi"] < 0.1
    assert row["band"] == "安定"


@pytest.mark.unit
def test_monitor_shifted_distribution_is_alert() -> None:
    # 3σ の平行移動：配信の質量の大半が基準の最上位ビン（p90〜）より外へ寄る → psi は 0.25 を大きく超える。
    values = np.random.default_rng(0).normal(size=500)
    baseline = pl.DataFrame({"x1": values})
    served = served_from(pl.DataFrame({"x1": values + 3.0}))
    row = monitor.monitor(baseline, served).psi.to_dicts()[0]
    assert row["psi"] > 0.25
    assert row["band"] == "大変化"


@pytest.mark.unit
def test_monitor_columns_restricts_targets() -> None:
    rng = np.random.default_rng(0)
    baseline = pl.DataFrame({"x1": rng.normal(size=50), "x2": rng.normal(size=50)})
    served = served_from(pl.DataFrame({"x1": rng.normal(size=50), "x2": rng.normal(size=50)}))
    report = monitor.monitor(baseline, served, columns=["x1"])
    assert report.psi["column"].to_list() == ["x1"]


@pytest.mark.unit
def test_monitor_skips_dtype_mismatch_with_warning() -> None:
    # x1 は基準=数値・配信=文字列（スキーマ不一致）→ 警告して読み飛ばし。cat は両側カテゴリ → psi は出る。
    baseline = pl.DataFrame({"x1": [1.0, 2.0], "cat": ["a", "b"]})
    served = served_from(pl.DataFrame({"x1": ["oops", "oops"], "cat": ["a", "b"]}))
    with pytest.warns(UserWarning, match="x1"):
        report = monitor.monitor(baseline, served)
    assert report.psi["column"].to_list() == ["cat"]


@pytest.mark.unit
def test_monitor_empty_log_degrades_without_failure() -> None:
    baseline = pl.DataFrame({"x1": [1.0, 2.0, 3.0]})
    empty = monitor.ServedLog(features=pl.DataFrame(), prediction_kinds=[], predictions=[], n_skipped=0)
    with pytest.warns(UserWarning):  # 空ログ＋ --auc 計算不能の縮退を知らせる（失敗にはしない）
        report = monitor.monitor(baseline, empty, auc=True, seed=0)
    assert report.n_served == 0
    assert report.psi.height == 0  # 片側 0 行の psi は意味を持たないので出さない
    assert report.drift is None
    assert report.prediction_summary == []


@pytest.mark.unit
def test_prediction_summary_values_follow_construction() -> None:
    # 定数 0.25 の proba：平均・全分位とも 0.25。多クラス [0.2, 0.8]：クラス別平均が 0.2 / 0.8。
    flat = monitor.ServedLog(
        features=pl.DataFrame({"x1": [0.0] * 8}),
        prediction_kinds=["proba"] * 8,
        predictions=[0.25] * 8,
        n_skipped=0,
    )
    (entry,) = monitor.prediction_summary(flat)
    assert entry["prediction_kind"] == "proba" and entry["n"] == 8
    assert entry["mean"] == pytest.approx(0.25)
    assert set(entry["quantiles"]) == {"p05", "p25", "p50", "p75", "p95"}
    assert all(v == pytest.approx(0.25) for v in entry["quantiles"].values())

    multi = monitor.ServedLog(
        features=pl.DataFrame({"x1": [0.0] * 5}),
        prediction_kinds=["multiclass_proba"] * 5,
        predictions=[[0.2, 0.8]] * 5,
        n_skipped=0,
    )
    (entry,) = monitor.prediction_summary(multi)
    assert entry["prediction_kind"] == "multiclass_proba" and entry["n"] == 5
    means = [c["mean"] for c in entry["classes"]]
    assert means == [pytest.approx(0.2), pytest.approx(0.8)]


@pytest.mark.integration
def test_monitor_drift_auc_near_half_and_one() -> None:
    # adversarial validation の結線（eda.drift_auc へ委譲）：同一分布 ≈0.5・10σ ずらし ≈1.0。
    baseline = pl.DataFrame({"x1": np.random.default_rng(0).normal(size=300)})
    same = served_from(pl.DataFrame({"x1": np.random.default_rng(1).normal(size=300)}))
    apart = served_from(pl.DataFrame({"x1": np.random.default_rng(1).normal(size=300) + 10.0}))

    near_half = monitor.monitor(baseline, same, auc=True, seed=0)
    assert near_half.drift is not None
    assert near_half.drift["columns"] == ["x1"]
    assert 0.35 <= near_half.drift["auc"] <= 0.65

    near_one = monitor.monitor(baseline, apart, auc=True, seed=0)
    assert near_one.drift is not None
    assert near_one.drift["auc"] >= 0.95
    assert len(near_one.drift["fold_aucs"]) == 5


# ---- CLI（data monitor＝data compare 同型の YAML・exit 0・既定 glob） ----

BASELINE_SCHEMA = {
    "id": "monitor_base",
    "description": "data monitor の学習基準テーブル（テスト用）",
    "layer": "processed",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
    ],
}


def _project_with_baseline(make_project: Callable[..., Any], n: int = 500) -> Any:  # noqa: ANN401
    proj = make_project()
    proj.add_schema(BASELINE_SCHEMA)
    rng = np.random.default_rng(0)
    df = pl.DataFrame({"id": np.arange(n), "x1": rng.normal(size=n), "x2": rng.normal(size=n)})
    store.save(proj.root, df, "monitor_base")
    return proj


@pytest.mark.integration
def test_cli_monitor_reports_shift_via_default_glob(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # x1 は 3σ ずらす（大変化）・x2 は同一分布（安定。バイアス ≈ 9×(1/500+1/500)=0.036 ≪ 0.1）。
    proj = _project_with_baseline(make_project)
    rng = np.random.default_rng(1)
    feats = [
        {"x1": float(v1) + 3.0, "x2": float(v2)}
        for v1, v2 in zip(rng.normal(size=500), rng.normal(size=500), strict=True)
    ]
    write_log(
        proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "20260706.jsonl",
        [log_line(f, prediction=0.5, row=i) for i, f in enumerate(feats)],
    )
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, ["monitor", "--baseline", "monitor_base", "--auc", "--seed", "0"])
    assert result.exit_code == 0, f"data monitor が失敗: exc={result.exception!r} {result.output}"
    out = dict(yaml.safe_load(result.output))
    # data compare 同型の骨格（baseline/log/n_baseline/n_served/psi/drift/prediction_summary）
    assert out["baseline"] == "monitor_base"
    assert out["log"] == "artifacts/serve/predictions/**/*.jsonl"  # 既定 glob で拾えている
    assert out["n_baseline"] == 500 and out["n_served"] == 500
    bands = {r["column"]: r["band"] for r in out["psi"]}
    assert bands == {"x1": "大変化", "x2": "安定"}  # id は配信 features に無い＝共通列にならない
    assert set(out["drift"]["columns"]) == {"x1", "x2"}
    assert out["drift"]["auc"] >= 0.95  # x1 の 3σ ずれで概ね分離できる
    (summary,) = out["prediction_summary"]
    assert summary["prediction_kind"] == "proba" and summary["n"] == 500
    assert summary["mean"] == pytest.approx(0.5)  # 全行 0.5 で書いた


@pytest.mark.integration
def test_cli_monitor_since_and_columns_options(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project_with_baseline(make_project, n=10)
    write_log(
        proj.root / "artifacts" / "serve" / "predictions" / "baseline" / "mixed.jsonl",
        [
            log_line({"x1": 1.0, "x2": 1.0}, prediction=0.5, time="2026-07-01T00:00:00+00:00"),
            log_line({"x1": 2.0, "x2": 2.0}, prediction=0.5, time="2026-07-06T00:00:00+00:00"),
        ],
    )
    monkeypatch.chdir(proj.root)

    args = ["monitor", "--baseline", "monitor_base", "--since", "2026-07-03", "--columns", "x1"]
    result = runner.invoke(data_app, args)
    assert result.exit_code == 0, f"data monitor が失敗: exc={result.exception!r} {result.output}"
    out = dict(yaml.safe_load(result.output))
    assert out["n_served"] == 1  # 7/1 の行は --since で落ちる
    assert [r["column"] for r in out["psi"]] == ["x1"]  # --columns で絞る

    bad = runner.invoke(data_app, ["monitor", "--baseline", "monitor_base", "--since", "07/03/2026"])
    assert bad.exit_code != 0  # 日付の書式違いは usage error（黙って全件にしない）


@pytest.mark.integration
def test_cli_monitor_empty_log_exits_zero(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # ログが 1 行も無い＝監視の縮退（exit 0・n_served 0）。門番にしない。
    proj = _project_with_baseline(make_project, n=10)
    monkeypatch.chdir(proj.root)
    result = runner.invoke(data_app, ["monitor", "--baseline", "monitor_base"])
    assert result.exit_code == 0, f"空ログで非 0: exc={result.exception!r} {result.output}"
    out = dict(yaml.safe_load(result.output))
    assert out["n_served"] == 0
    assert out["psi"] == []
    assert out["prediction_summary"] == []


@pytest.mark.integration
def test_cli_monitor_unreadable_baseline_exits_nonzero(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 基準テーブルが読めない（未保存・定義なし）は読込不能＝非 0（ここだけは黙って 0 にしない）。
    proj = make_project()
    monkeypatch.chdir(proj.root)
    result = runner.invoke(data_app, ["monitor", "--baseline", "no_such_table"])
    assert result.exit_code != 0


@pytest.mark.integration
def test_cli_monitor_registered_in_help() -> None:
    result = runner.invoke(data_app, ["--help"])
    assert result.exit_code == 0
    assert "monitor" in result.output  # typer への登録（配線）の証拠
