"""答え合わせ（ds/scoring.py）のテスト。

期待値はすべてデータ構成から導く：
- 完全分離のスコア（0.9/0.1）を 0.5 で閾値化すればラベルは符号どおり → 実測 accuracy は当たり数から一意。
- 相対劣化は (約束 - 実測)/|約束|（大きいほど良い指標）から手計算できる。
乱数は使わない（データは決定的に構成する）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from harness.ds import scoring
from harness.ds.scoring import ScoredPredictions


def _scored(fingerprints: list[str], predictions: list[Any], kind: str) -> ScoredPredictions:
    return ScoredPredictions(
        input_fingerprints=fingerprints,
        predictions=predictions,
        prediction_kinds=[kind] * len(fingerprints),
        n_skipped=0,
    )


@pytest.mark.unit
def test_band_thresholds_follow_constants() -> None:
    # 0.05 未満=安定・0.05〜0.10=要注意・0.10 以上=大変化・None=基準なし（定数からそのまま）。
    assert scoring.degradation_band(0.0) == "安定"
    assert scoring.degradation_band(scoring.DEGRADE_WATCH - 1e-9) == "安定"
    assert scoring.degradation_band(scoring.DEGRADE_WATCH) == "要注意"
    assert scoring.degradation_band(scoring.DEGRADE_ALERT - 1e-9) == "要注意"
    assert scoring.degradation_band(scoring.DEGRADE_ALERT) == "大変化"
    assert scoring.degradation_band(None) == "基準なし"


@pytest.mark.unit
def test_perfect_binary_realized_matches_and_band_stable() -> None:
    # スコア 0.9/0.9/0.1/0.1 を 0.5 で閾値化→ラベル 1/1/0/0。実績も 1/1/0/0＝全問正解＝accuracy 1.0。
    scored = _scored(["a", "b", "c", "d"], [0.9, 0.9, 0.1, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b", "c", "d"], "y": [1, 1, 0, 0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"], promised={"accuracy": 1.0})
    assert report.task == "binary"  # kind=proba から導出
    assert report.n_matched == 4
    (acc,) = report.comparisons
    assert acc.metric == "accuracy"
    assert acc.realized == 1.0
    assert acc.delta == 0.0  # 1.0 - 1.0
    assert acc.relative_degradation == 0.0  # 実測が約束と同等
    assert acc.band == "安定"


@pytest.mark.unit
def test_degraded_binary_flags_big_change() -> None:
    # ラベルは 1/0/0/1（スコア 0.9/0.1/0.1/0.9）だが実績は 1/1/0/0＝2 問正解＝accuracy 0.5。
    # 約束 1.0 に対し相対劣化 = (1.0 - 0.5)/1.0 = 0.5 ≥ 0.10 ＝大変化。
    scored = _scored(["a", "b", "c", "d"], [0.9, 0.1, 0.1, 0.9], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b", "c", "d"], "y": [1, 1, 0, 0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"], promised={"accuracy": 1.0})
    (acc,) = report.comparisons
    assert acc.realized == 0.5
    assert acc.delta == -0.5
    assert acc.relative_degradation == 0.5
    assert acc.band == "大変化"


@pytest.mark.unit
def test_promised_absent_gives_no_baseline_band() -> None:
    # promised を渡さなければ delta/相対劣化は None・band は「基準なし」。
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1, 0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    (acc,) = report.comparisons
    assert acc.promised is None
    assert acc.delta is None
    assert acc.relative_degradation is None
    assert acc.band == "基準なし"


@pytest.mark.unit
def test_join_counts_from_set_overlap() -> None:
    # 予測 {a,b,c}・実績 {b,c,d}＝共通 {b,c}。予測のみ={a}・実績のみ={d}。
    scored = _scored(["a", "b", "c"], [0.9, 0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["b", "c", "d"], "y": [1, 0, 1]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.n_predicted == 3
    assert report.n_actual == 3
    assert report.n_matched == 2
    assert report.n_unmatched_predictions == 1  # a
    assert report.n_unmatched_actuals == 1  # d


@pytest.mark.unit
def test_regression_realized_and_lower_is_better_degradation() -> None:
    # 予測 [2,4,6]・実績 [1,2,3]＝残差 [1,2,3]→ rmse = sqrt((1+4+9)/3) = sqrt(14/3)。
    # 約束 rmse=1.0（小さいほど良い）に対し実測が悪化＝相対劣化 (実測-約束)/|約束|。
    import numpy as np

    scored = _scored(["a", "b", "c"], [2.0, 4.0, 6.0], "value")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b", "c"], "y": [1.0, 2.0, 3.0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["rmse"], promised={"rmse": 1.0})
    (rmse,) = report.comparisons
    expected = float(np.sqrt((1.0 + 4.0 + 9.0) / 3.0))
    assert rmse.realized == pytest.approx(expected)
    assert rmse.relative_degradation == pytest.approx((expected - 1.0) / 1.0)  # 小さいほど良い→高いほど劣化
    assert rmse.band == "大変化"


@pytest.mark.unit
def test_multiclass_realized_from_argmax() -> None:
    # 3 クラスの確率。argmax がそのままクラス＝実績と一致させれば accuracy 1.0。
    rows = [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]]
    scored = _scored(["a", "b", "c"], rows, "multiclass_proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b", "c"], "y": [0, 1, 2]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.task == "multiclass"
    (acc,) = report.comparisons
    assert acc.realized == 1.0


@pytest.mark.unit
def test_mixed_kinds_raise() -> None:
    scored = ScoredPredictions(
        input_fingerprints=["a", "b"], predictions=[0.9, 1.0], prediction_kinds=["proba", "value"], n_skipped=0
    )
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1, 0]})
    with pytest.raises(ValueError, match="混在"):
        scoring.answer_check(scored, actuals, actual_column="y")


@pytest.mark.unit
def test_task_conflict_with_kind_raises() -> None:
    scored = _scored(["a"], [0.9], "proba")  # proba→binary
    actuals = pl.DataFrame({"input_fingerprint": ["a"], "y": [1]})
    with pytest.raises(ValueError, match="食い違う"):
        scoring.answer_check(scored, actuals, actual_column="y", task="regression")


@pytest.mark.unit
def test_conflicting_prediction_for_same_fingerprint_is_excluded() -> None:
    # 同じ指紋 a に食い違う予測（0.9 と 0.1）＝版混在の疑い→ a を除外し警告。残る b だけで測る。
    scored = _scored(["a", "a", "b"], [0.9, 0.1, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1, 0]})
    with pytest.warns(UserWarning, match="食い違う"):
        report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.n_predicted == 1  # a は除外・b だけ
    assert report.n_matched == 1


@pytest.mark.unit
def test_duplicate_actual_key_raises() -> None:
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "a"], "y": [1, 0]})  # 鍵 a が重複
    with pytest.raises(ValueError, match="重複"):
        scoring.answer_check(scored, actuals, actual_column="y")


@pytest.mark.unit
def test_null_actual_key_is_dropped_with_warning() -> None:
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", None], "y": [1, 0]})  # b の鍵が欠損
    with pytest.warns(UserWarning, match="欠損"):
        report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.n_actual == 1  # 欠損行を除外
    assert report.n_matched == 1  # a だけ突き合う


@pytest.mark.unit
def test_no_match_emits_no_metrics() -> None:
    # 予測と実績の鍵が一切重ならない＝突き合わせ 0＝指標は出さない（警告つき）。
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["x", "y"], "y": [1, 0]})
    with pytest.warns(UserWarning, match="突き合わさった行が 0"):
        report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.n_matched == 0
    assert report.comparisons == []


@pytest.mark.unit
def test_missing_key_or_actual_column_raises() -> None:
    scored = _scored(["a"], [0.9], "proba")
    with pytest.raises(ValueError, match="鍵の列"):
        scoring.answer_check(scored, pl.DataFrame({"y": [1]}), actual_column="y")
    with pytest.raises(ValueError, match="正解の列"):
        scoring.answer_check(scored, pl.DataFrame({"input_fingerprint": ["a"]}), actual_column="y")


@pytest.mark.unit
def test_empty_predictions_returns_empty_report_not_raise() -> None:
    # 予測 0 行（版フィルタ・未流入）＝門番にしない：空の表を返す（例外で定期実行を落とさない＝H1 の回帰）。
    scored = ScoredPredictions(input_fingerprints=[], predictions=[], prediction_kinds=[], n_skipped=0)
    actuals = pl.DataFrame({"input_fingerprint": ["a"], "y": [1]})
    with pytest.warns(UserWarning, match="対象行が 0"):
        report = scoring.answer_check(scored, actuals, actual_column="y")
    assert report.n_predicted == 0
    assert report.n_matched == 0
    assert report.comparisons == []
    assert report.task == "unknown"  # 予測も task 指定も無い＝ラベルは unknown（落とさない）


@pytest.mark.unit
def test_zero_promise_degradation_is_infinite_not_no_baseline() -> None:
    # 約束 rmse=0.0（完全予測の約束）で実測が悪化＝比は定義できないが劣化は本物→inf→大変化（M3 の回帰）。
    scored = _scored(["a", "b"], [2.0, 4.0], "value")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1.0, 1.0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["rmse"], promised={"rmse": 0.0})
    (rmse,) = report.comparisons
    assert rmse.realized > 0.0
    assert rmse.relative_degradation == float("inf")
    assert rmse.band == "大変化"


@pytest.mark.unit
def test_zero_promise_perfect_realized_is_stable() -> None:
    # 約束 rmse=0.0 で実測も 0.0（完全一致）＝劣化なし→0.0→安定（0 を「基準なし」に丸めない・inf にもしない）。
    scored = _scored(["a", "b"], [1.0, 2.0], "value")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1.0, 2.0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["rmse"], promised={"rmse": 0.0})
    (rmse,) = report.comparisons
    assert rmse.realized == 0.0
    assert rmse.relative_degradation == 0.0
    assert rmse.band == "安定"


@pytest.mark.unit
def test_nan_actual_row_dropped_with_warning() -> None:
    # 実績が NaN の行は sklearn を不透明に落とす前に除外（門番にしない＝残りで測る。M4 の回帰）。
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1.0, float("nan")]})
    with pytest.warns(UserWarning, match="NaN"):
        report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"])
    assert report.n_matched == 1  # b の実績 NaN を除外
    assert report.comparisons[0].realized == 1.0


@pytest.mark.unit
def test_unmatched_promised_metric_warns() -> None:
    # 約束したのに実測側に無い指標（--metrics で絞った）は黙って未照合にしない＝警告（L1 の回帰）。
    scored = _scored(["a", "b"], [0.9, 0.1], "proba")
    actuals = pl.DataFrame({"input_fingerprint": ["a", "b"], "y": [1, 0]})
    with pytest.warns(UserWarning, match="未照合"):
        scoring.answer_check(
            scored, actuals, actual_column="y", metrics=["accuracy"], promised={"accuracy": 1.0, "roc_auc": 0.99}
        )


# ---- 課題起票の内容（決定的・冪等） ----


@pytest.mark.unit
def test_issue_fingerprint_is_deterministic_and_metric_scoped() -> None:
    from datetime import date

    from harness.ds.scoring import MetricComparison

    deg = [MetricComparison("accuracy", 0.5, 1.0, -0.5, 0.5, "大変化")]
    c1 = scoring.score_issue_content(model="w/n", log="l", actuals="a.parquet", degraded=deg, today=date(2026, 7, 11))
    c2 = scoring.score_issue_content(model="w/n", log="l", actuals="a.parquet", degraded=deg, today=date(2026, 12, 31))
    assert c1.fingerprint == c2.fingerprint  # 日付・劣化率は指紋に含めない＝同じ事象は 1 件
    # 指標集合が変われば別事象＝別指紋。
    deg2 = deg + [MetricComparison("roc_auc", 0.5, 0.9, -0.4, 0.44, "大変化")]
    c3 = scoring.score_issue_content(model="w/n", log="l", actuals="a.parquet", degraded=deg2, today=date(2026, 7, 11))
    assert c3.fingerprint != c1.fingerprint


# ---- 予測ログの読み取り（契約・壊れ行の読み飛ばし・版/role/since の絞り込み） ----


def _write_log(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _row(
    fp: str, pred: object, *, version: str = "v1", role: str = "primary", time: str = "2026-07-11T00:00:00"
) -> dict[str, object]:
    # PREDICTION_LOG_FIELDS の契約に沿った 1 行（proba）。
    return {
        "time": time,
        "request_id": "req",
        "row": 0,
        "model": {"work": "w", "name": "n", "version": version, "fingerprint": "fp"},
        "prediction_kind": "proba",
        "input_fingerprint": fp,
        "features": {"x": 1.0},
        "prediction": pred,
        "role": role,
    }


@pytest.mark.unit
def test_reader_keeps_fingerprint_and_prediction(tmp_path: Path) -> None:
    log = tmp_path / "p.jsonl"
    _write_log(log, [_row("a", 0.9), _row("b", 0.1)])
    scored = scoring.read_scored_predictions([log])
    assert scored.input_fingerprints == ["a", "b"]
    assert scored.predictions == [0.9, 0.1]
    assert scored.n_rows == 2


@pytest.mark.unit
def test_reader_skips_row_missing_fingerprint(tmp_path: Path) -> None:
    log = tmp_path / "p.jsonl"
    good = _row("a", 0.9)
    bad = _row("b", 0.1)
    del bad["input_fingerprint"]  # 契約は満たすが答え合わせに要る指紋が無い
    _write_log(log, [good, bad])
    with pytest.warns(UserWarning, match="input_fingerprint"):
        scored = scoring.read_scored_predictions([log])
    assert scored.input_fingerprints == ["a"]
    assert scored.n_skipped == 1


@pytest.mark.unit
def test_reader_version_and_role_filters(tmp_path: Path) -> None:
    log = tmp_path / "p.jsonl"
    _write_log(
        log,
        [
            _row("a", 0.9, version="v1", role="primary"),
            _row("b", 0.8, version="v2", role="primary"),  # 版違い
            _row("c", 0.7, version="v1", role="shadow"),  # role 違い
        ],
    )
    scored = scoring.read_scored_predictions([log], version="v1", role="primary")
    assert scored.input_fingerprints == ["a"]  # v1 かつ primary だけ


@pytest.mark.unit
def test_reader_since_filters_by_date(tmp_path: Path) -> None:
    from datetime import date

    log = tmp_path / "p.jsonl"
    _write_log(
        log,
        [
            _row("old", 0.9, time="2026-07-01T00:00:00"),
            _row("new", 0.1, time="2026-07-11T00:00:00"),
        ],
    )
    scored = scoring.read_scored_predictions([log], since=date(2026, 7, 11))
    assert scored.input_fingerprints == ["new"]  # 境界日を含む・それより前は落ちる


@pytest.mark.unit
def test_reader_skips_corrupt_model_when_version_filtering(tmp_path: Path) -> None:
    # 版で絞るのに model が dict でない行は、黙って握り潰さず壊れ行として読み飛ばす（M1 の回帰）。
    log = tmp_path / "p.jsonl"
    good = _row("a", 0.9, version="v1")
    bad = _row("b", 0.1)
    bad["model"] = "corrupt"  # dict でない（version 絞り込みが .get で落ちていた）
    _write_log(log, [good, bad])
    with pytest.warns(UserWarning, match="model"):
        scored = scoring.read_scored_predictions([log], version="v1")
    assert scored.input_fingerprints == ["a"]
    assert scored.n_skipped == 1


@pytest.mark.unit
def test_reader_skips_ragged_multiclass(tmp_path: Path) -> None:
    # 多クラスの確率の長さが揃わない行は np.asarray で落ちる前に読み飛ばす（monitor と同じ・M2 の回帰）。
    log = tmp_path / "p.jsonl"
    r1 = _row("a", [0.7, 0.2, 0.1])
    r1["prediction_kind"] = "multiclass_proba"
    r2 = _row("b", [0.5, 0.5])  # 長さ 2（基準は 3）
    r2["prediction_kind"] = "multiclass_proba"
    _write_log(log, [r1, r2])
    with pytest.warns(UserWarning, match="長さ"):
        scored = scoring.read_scored_predictions([log])
    assert scored.input_fingerprints == ["a"]
    assert scored.n_skipped == 1


@pytest.mark.unit
def test_reader_skips_nan_prediction(tmp_path: Path) -> None:
    # NaN の予測は答え合わせに使えない＝壊れ行として読み飛ばす（sklearn で不透明に落ちる前に。M4 の回帰）。
    log = tmp_path / "p.jsonl"
    _write_log(log, [_row("a", 0.9), _row("b", float("nan"))])
    with pytest.warns(UserWarning, match="NaN"):
        scored = scoring.read_scored_predictions([log])
    assert scored.input_fingerprints == ["a"]
    assert scored.n_skipped == 1


@pytest.mark.integration
def test_reader_matches_serve_runtime_contract(tmp_path: Path) -> None:
    # serve が実際に書く行（build_log_rows）を読めることを確かめる（契約の両側が一致している証拠）。
    import numpy as np

    from harness.ds.models import ModelRecord
    from harness.serve import runtime

    record = ModelRecord(
        name="n",
        work="w",
        version="v1",
        format="pickle",
        fingerprint="fp",
        data_fingerprint="df",
        feature_names=("x",),
        config={},
        metrics={"accuracy": 1.0},
        python="3.14",
        dependencies={},
        created="2026-07-11T00:00:00",
        path=tmp_path / "manifest.yaml",
    )
    rows = runtime.build_log_rows(
        record=record,
        prediction_kind="proba",
        features_rows=[{"x": 1.0}, {"x": 2.0}],
        predictions=np.array([0.9, 0.1]),
        request_id="req",
        time="2026-07-11T00:00:00",
    )
    log = tmp_path / "p.jsonl"
    _write_log(log, rows)
    scored = scoring.read_scored_predictions([log], version="v1")
    assert scored.n_rows == 2
    assert scored.prediction_kinds == ["proba", "proba"]
    # serve が計算した指紋で答え合わせできる（実績を同じ指紋で用意すれば突き合う）。
    actuals = pl.DataFrame({"input_fingerprint": scored.input_fingerprints, "y": [1, 0]})
    report = scoring.answer_check(scored, actuals, actual_column="y", metrics=["accuracy"], promised=record.metrics)
    assert report.n_matched == 2
    assert report.comparisons[0].realized == 1.0
