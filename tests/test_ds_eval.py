"""評価ハーネスのテスト：指標の算出と、設定の閾値による合否判定。"""

from __future__ import annotations

import numpy as np
import pytest

from harness.ds import eval as ev

pytestmark = pytest.mark.unit


def test_perfect_predictions_score_top() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    metrics = ev.evaluate(y_true, y_score)
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0


def test_reversed_predictions_score_bottom() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.9, 0.8, 0.2, 0.1], dtype="float64")
    assert ev.evaluate(y_true, y_score)["roc_auc"] == 0.0


def test_auc_is_half_without_both_classes() -> None:
    y_true = np.array([1, 1, 1], dtype="int64")
    y_score = np.array([0.2, 0.5, 0.9], dtype="float64")
    assert ev.roc_auc(y_true, y_score) == 0.5


def test_select_threshold_max_f1_exact() -> None:
    # y=[0,0,1,1], s=[.1,.4,.6,.9]。閾値 0.6 で pred=[0,0,1,1]＝P=R=1・F1=1.0（構成から厳密）。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    threshold, f1 = ev.select_threshold_max_f1(y, s)
    assert threshold == 0.6
    assert f1 == 1.0


def test_select_threshold_max_f1_ties_prefer_larger() -> None:
    # y=[1,0,0,1], s=[.9,.7,.5,.2]。F1 最大 2/3 が閾値 0.2 と 0.9 で同点 → 大きい方 0.9 を返す。
    y = np.array([1, 0, 0, 1], dtype="int64")
    s = np.array([0.9, 0.7, 0.5, 0.2], dtype="float64")
    threshold, f1 = ev.select_threshold_max_f1(y, s)
    assert threshold == 0.9
    assert f1 == pytest.approx(2 / 3)


def test_select_threshold_at_recall() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    assert ev.select_threshold_at_recall(y, s, target=1.0) == 0.6  # 両正例を拾う最大の閾値
    assert ev.select_threshold_at_recall(y, s, target=0.5) == 0.9  # 再現率 0.5 を満たす最大


def test_select_threshold_at_precision() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    assert ev.select_threshold_at_precision(y, s, target=1.0) == 0.6  # 適合率 1 を満たす最小の閾値


def test_select_threshold_at_precision_unreachable() -> None:
    # どの閾値でも適合率 1 に届かない → max(y_score) より上（全部陰性）を返す。
    y = np.array([1, 0], dtype="int64")
    s = np.array([0.3, 0.8], dtype="float64")
    assert ev.select_threshold_at_precision(y, s, target=1.0) > 0.8


def test_select_threshold_single_class_is_error() -> None:
    with pytest.raises(ValueError, match="両方"):
        ev.select_threshold_max_f1(np.array([1, 1, 1], dtype="int64"), np.array([0.2, 0.5, 0.9], dtype="float64"))


def test_passes_requires_all_thresholds() -> None:
    metrics = {"accuracy": 0.8, "roc_auc": 0.85}
    # すべての閾値を満たす → 成功。
    assert ev.passes(metrics, {"accuracy": 0.75, "roc_auc": 0.8})
    # ひとつでも下回る → 失敗。
    assert not ev.passes(metrics, {"accuracy": 0.9})
    # 閾値に無い指標は判定に使わない（空の閾値は常に成功）。
    assert ev.passes(metrics, {})


def test_metrics_registry_covers_classification_and_regression() -> None:
    # 分類・回帰の両タスクが登録され、向きが指標の属性として持たれる。
    assert ev.METRICS["roc_auc"].higher_is_better is True
    assert ev.METRICS["log_loss"].higher_is_better is False  # 小さいほど良い
    assert ev.METRICS["rmse"].task == "regression"
    assert ev.METRICS["accuracy"].input == "label"  # 閾値後のラベルで測る
    assert ev.METRICS["roc_auc"].input == "score"  # 確率で測る


def test_evaluate_returns_all_classification_metrics() -> None:
    y_true = np.array([0, 0, 1, 1], dtype="int64")
    y_score = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    metrics = ev.evaluate(y_true, y_score)
    # 完全予測：確率系も閾値後のラベル系もすべて満点（構成から導出）。
    for name in ("accuracy", "roc_auc", "pr_auc", "f1", "precision", "recall"):
        assert metrics[name] == 1.0, name
    assert metrics["log_loss"] >= 0.0  # 小さいほど良い（0 以上）
    # metrics= で選べる（回帰指標名を渡すと拒否）。
    assert set(ev.evaluate(y_true, y_score, metrics=["roc_auc"])) == {"roc_auc"}
    with pytest.raises(ValueError, match="回帰|分類"):
        ev.evaluate(y_true, y_score, metrics=["rmse"])


def test_evaluate_regression_values_from_construction() -> None:
    # y_true=[0,0], y_pred=[3,4] → mae=(3+4)/2=3.5・rmse=√((9+16)/2)=√12.5（電卓で導ける）。
    y_true = np.array([0.0, 0.0], dtype="float64")
    y_pred = np.array([3.0, 4.0], dtype="float64")
    m = ev.evaluate_regression(y_true, y_pred)
    assert m["mae"] == pytest.approx(3.5)
    assert m["rmse"] == pytest.approx(np.sqrt(12.5))


def test_passes_respects_direction_and_rejects_unknown() -> None:
    # log_loss は小さいほど良い：0.4 は閾値 0.5 で合格・0.6 は不合格。
    assert ev.passes({"log_loss": 0.4}, {"log_loss": 0.5})
    assert not ev.passes({"log_loss": 0.6}, {"log_loss": 0.5})
    # roc_auc は大きいほど良い（従来どおり）。
    assert ev.passes({"roc_auc": 0.85}, {"roc_auc": 0.8})
    # 未登録の指標名は typo を黙って不合格にせず ValueError。
    with pytest.raises(ValueError, match="未登録|未知"):
        ev.passes({"roc_auc": 0.85}, {"nope": 0.5})


def test_passes_nan_fails_closed() -> None:
    # NaN はどの比較とも False（比較が常に偽）→ 素通り（fail open）せず、両向きとも不合格にする。
    # 発散したモデル（log_loss=nan・rmse=nan 等）が判定を通って昇格してはいけない。
    assert not ev.passes({"roc_auc": float("nan")}, {"roc_auc": 0.8})  # 大きいほど良い向き
    assert not ev.passes({"log_loss": float("nan")}, {"log_loss": 0.5})  # 小さいほど良い向き
    # 通常の合否は従来どおり（境界値＝閾値ちょうどは合格）。
    assert ev.passes({"roc_auc": 0.8}, {"roc_auc": 0.8})
    assert not ev.passes({"roc_auc": 0.75}, {"roc_auc": 0.8})
    assert ev.passes({"log_loss": 0.5}, {"log_loss": 0.5})
    assert not ev.passes({"log_loss": 0.6}, {"log_loss": 0.5})


def test_evaluate_single_class_edges_absorbed() -> None:
    # 単一クラス（y 全 0）でも log_loss は落ちない・pr_auc は方針値 0.0（docstring と一致）。
    y_true = np.array([0, 0, 0], dtype="int64")
    y_score = np.array([0.2, 0.5, 0.9], dtype="float64")
    m = ev.evaluate(y_true, y_score)
    assert np.isfinite(m["log_loss"])
    assert m["pr_auc"] == 0.0


def test_evaluate_multiclass_perfect_from_construction() -> None:
    # 3 クラス各 4 行。proba は正解クラス 0.8・他 0.1（行和 1）→ argmax が常に正解＝label 系は満点、
    # macro_roc_auc も順位が完全なので 1.0、log_loss_multi は全行 -log(0.8)（すべて構成から導出）。
    y = np.repeat(np.arange(3), 4).astype("int64")
    proba = np.full((12, 3), 0.1, dtype="float64")
    proba[np.arange(12), y] = 0.8
    m = ev.evaluate_multiclass(y, proba)
    for name in ("accuracy", "macro_f1", "macro_precision", "macro_recall", "macro_roc_auc"):
        assert m[name] == 1.0, name
    assert m["log_loss_multi"] == pytest.approx(-np.log(0.8))


def test_evaluate_multiclass_random_near_chance() -> None:
    # 3 クラス均衡 900 行・予測は真値と独立の一様乱数ラベル → accuracy/macro_f1 の期待値は 1/3。
    # 標準誤差 ≈ sqrt((1/3)(2/3)/900) ≈ 0.016 → ±0.08 は 5σ（境界は構成から導く・実装出力の写経ではない）。
    rng = np.random.default_rng(0)
    y = np.repeat(np.arange(3), 300).astype("int64")
    guess = rng.integers(0, 3, size=900)
    proba = np.full((900, 3), 0.1, dtype="float64")
    proba[np.arange(900), guess] = 0.8
    m = ev.evaluate_multiclass(y, proba, metrics=["accuracy", "macro_f1"])
    assert m["accuracy"] == pytest.approx(1 / 3, abs=0.08)
    assert m["macro_f1"] == pytest.approx(1 / 3, abs=0.08)


def test_evaluate_multiclass_rejects_mismatched_metrics_and_shape() -> None:
    y3 = np.repeat(np.arange(3), 2).astype("int64")
    proba = np.full((6, 3), 1 / 3, dtype="float64")
    # 二値指標を multiclass に混ぜたら ValueError（tasks 不一致）。
    with pytest.raises(ValueError, match="二値"):
        ev.evaluate_multiclass(y3, proba, metrics=["f1"])
    # 逆向き：多クラス指標を二値 evaluate に混ぜても ValueError。
    y2 = np.array([0, 1, 0, 1], dtype="int64")
    s2 = np.array([0.1, 0.9, 0.2, 0.8], dtype="float64")
    with pytest.raises(ValueError, match="多クラス"):
        ev.evaluate(y2, s2, metrics=["macro_f1"])
    # proba が 1 次元なら明確に失敗（多クラスは (n, n_classes) が契約）。
    with pytest.raises(ValueError, match="n_classes"):
        ev.evaluate_multiclass(y3, np.full(6, 0.5, dtype="float64"))
    # 2 列（2 クラス）は多クラス経路でなく evaluate を使う。macro 指標が不透明に落ちる前に明示で止める。
    with pytest.raises(ValueError, match="2 クラスは evaluate"):
        ev.evaluate_multiclass(np.array([0, 1, 0, 1], dtype="int64"), np.full((4, 2), 0.5, dtype="float64"))


def test_metrics_registry_multiclass_vocabulary_and_passes() -> None:
    # 語彙：多クラス指標は tasks=("multiclass",)・accuracy は二値と多クラスの両方で測れる。既存の二値語彙は不変。
    assert ev.METRICS["macro_f1"].tasks == ("multiclass",)
    assert ev.METRICS["accuracy"].tasks == ("binary", "multiclass")
    assert ev.METRICS["f1"].tasks == ("binary",)
    assert ev.METRICS["rmse"].tasks == ("regression",)
    # 向きと入力：log_loss_multi は小さいほど良い・確率系は score・macro 平均系は label。
    assert ev.METRICS["log_loss_multi"].higher_is_better is False
    assert ev.METRICS["macro_roc_auc"].input == "score"
    assert ev.METRICS["macro_f1"].input == "label"
    # passes は登録済みの多クラス指標をそのまま判定できる（向きはレジストリで解決）。
    assert ev.passes({"macro_f1": 0.9}, {"macro_f1": 0.8})
    assert not ev.passes({"log_loss_multi": 0.6}, {"log_loss_multi": 0.5})


def test_metric_fn_for_multiclass() -> None:
    # metric_fn_for("multiclass") は evaluate_multiclass を包む（proba は (n, n_classes)・threshold 不使用）。
    fn = ev.metric_fn_for("multiclass", metrics=["accuracy", "macro_f1"])
    y = np.repeat(np.arange(3), 2).astype("int64")
    proba = np.full((6, 3), 0.1, dtype="float64")
    proba[np.arange(6), y] = 0.8
    assert fn(y, proba) == {"accuracy": 1.0, "macro_f1": 1.0}  # argmax が常に正解（構成から）


def test_confusion_from_construction() -> None:
    # y=[0,0,1,1], score=[0.9,0.1,0.8,0.2], 閾値 0.5 → pred=[1,0,1,0] → tn=fp=fn=tp==1。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.9, 0.1, 0.8, 0.2], dtype="float64")
    assert ev.confusion(y, s) == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}


def test_class_metrics_both_classes() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.9, 0.1, 0.8, 0.2], dtype="float64")  # pred=[1,0,1,0]
    rows = {r["class"]: r for r in ev.class_metrics(y, s).to_dicts()}
    assert set(rows) == {0, 1}  # 両クラスが出る
    assert rows[0]["precision"] == pytest.approx(0.5)  # pred=0 は 2 件・うち正しく 0 は 1 件
    assert rows[1]["recall"] == pytest.approx(0.5)  # 実際の 1 は 2 件・拾えたのは 1 件
    assert rows[0]["count"] == 2  # support


def test_calibration_table_single_bin() -> None:
    # score 全行 0.3・y は 4 行中 1 正例 → 1 ビン：count 4・fraction 0.25・mean_predicted 0.3。
    y = np.array([1, 0, 0, 0], dtype="int64")
    s = np.array([0.3, 0.3, 0.3, 0.3], dtype="float64")
    tbl = ev.calibration_table(y, s).to_dicts()
    assert len(tbl) == 1
    assert tbl[0]["count"] == 4
    assert tbl[0]["fraction_positive"] == pytest.approx(0.25)
    assert tbl[0]["mean_predicted"] == pytest.approx(0.3)


def test_r2_from_construction() -> None:
    # y=[1,2,3,4]：完全一致予測は残差 0 → r2=1.0。平均 2.5 の定数予測は残差平方和＝全平方和 → r2=0.0（定義から）。
    y = np.array([1.0, 2.0, 3.0, 4.0], dtype="float64")
    assert ev.evaluate_regression(y, y.copy(), metrics=["r2"])["r2"] == 1.0
    mean_pred = np.full(4, 2.5, dtype="float64")
    assert ev.evaluate_regression(y, mean_pred, metrics=["r2"])["r2"] == 0.0


def test_pinball_is_half_mae_at_default_alpha() -> None:
    # α=0.5 のピンボール損失は |誤差|×0.5 の平均＝mae/2。y=[0,0], pred=[3,4] → mae=3.5 → pinball=1.75（構成から）。
    y_true = np.array([0.0, 0.0], dtype="float64")
    y_pred = np.array([3.0, 4.0], dtype="float64")
    assert ev.evaluate_regression(y_true, y_pred, metrics=["pinball"])["pinball"] == pytest.approx(1.75)


def test_mcc_and_balanced_accuracy_binary_from_construction() -> None:
    # 完全一致（閾値 0.5 で pred=y）→ mcc=1.0・均衡正解率 1.0。スコア全反転で pred が全部外れ → mcc=-1.0・BA=0.0。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    m = ev.evaluate(y, s, metrics=["mcc", "balanced_accuracy"])
    assert m["mcc"] == 1.0
    assert m["balanced_accuracy"] == 1.0
    m2 = ev.evaluate(y, 1.0 - s, metrics=["mcc", "balanced_accuracy"])  # pred=[1,1,0,0]＝全外し
    assert m2["mcc"] == -1.0
    assert m2["balanced_accuracy"] == 0.0


def test_mcc_and_balanced_accuracy_multiclass_perfect() -> None:
    # 3 クラス各 2 行・proba は正解クラス 0.8 → argmax が常に正解＝どちらも 1.0（構成から）。
    y = np.repeat(np.arange(3), 2).astype("int64")
    proba = np.full((6, 3), 0.1, dtype="float64")
    proba[np.arange(6), y] = 0.8
    m = ev.evaluate_multiclass(y, proba, metrics=["mcc", "balanced_accuracy"])
    assert m["mcc"] == 1.0
    assert m["balanced_accuracy"] == 1.0


def test_new_metrics_registry_vocabulary() -> None:
    # 語彙と向き：r2/pinball は回帰・mcc/balanced_accuracy は二値と多クラス両方・calibration は 0 が最良（False）。
    assert ev.METRICS["r2"].tasks == ("regression",)
    assert ev.METRICS["r2"].higher_is_better is True
    assert ev.METRICS["pinball"].higher_is_better is False
    assert ev.METRICS["mcc"].tasks == ("binary", "multiclass")
    assert ev.METRICS["balanced_accuracy"].tasks == ("binary", "multiclass")
    assert ev.METRICS["calibration_gap"].input == "score"
    assert ev.METRICS["calibration_gap"].higher_is_better is False


def test_calibration_zero_when_means_match_and_grows_when_overpredicting() -> None:
    # mean(true)=0.5・mean(score)=0.5 → 比 1 → |1-1|=0（最良）。mean(score)=0.75 → 比 1.5 → 0.5（過大予測でずれ増）。
    y = np.array([0, 1, 0, 1], dtype="int64")
    s_matched = np.array([0.3, 0.7, 0.5, 0.5], dtype="float64")  # 平均 0.5
    assert ev.evaluate(y, s_matched, metrics=["calibration_gap"])["calibration_gap"] == 0.0
    s_over = np.array([0.6, 0.9, 0.7, 0.8], dtype="float64")  # 平均 0.75
    assert ev.evaluate(y, s_over, metrics=["calibration_gap"])["calibration_gap"] == pytest.approx(0.5)


def test_calibration_nan_when_no_positives() -> None:
    # y 全 0 → mean(true)=0 で比が定義できない → nan（docstring どおり・passes は NaN を不合格＝fail closed）。
    y = np.array([0, 0, 0], dtype="int64")
    s = np.array([0.2, 0.5, 0.9], dtype="float64")
    assert np.isnan(ev.evaluate(y, s, metrics=["calibration_gap"])["calibration_gap"])
    assert not ev.passes({"calibration_gap": float("nan")}, {"calibration_gap": 0.1})


def test_roc_table_perfect_separation() -> None:
    # 完全分離（順位が真値と一致）→ (fpr=0, tpr=1) の角の点が出る。fpr/tpr は [0,1]・threshold は降順（構成から）。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.2, 0.8, 0.9], dtype="float64")
    tbl = ev.roc_table(y, s)
    assert tbl.columns == ["fpr", "tpr", "threshold"]
    assert any(r["fpr"] == 0.0 and r["tpr"] == 1.0 for r in tbl.to_dicts())  # 角
    fpr, tpr, th = (tbl[c].to_numpy() for c in ("fpr", "tpr", "threshold"))
    assert ((fpr >= 0.0) & (fpr <= 1.0)).all()
    assert ((tpr >= 0.0) & (tpr <= 1.0)).all()
    assert (np.diff(th) < 0).all()  # 降順（先頭は番兵の inf）


def test_roc_table_max_points_thins_keeping_ends() -> None:
    # 100 点でも max_points=5 なら高々 5 行に間引かれ、端点（fpr=tpr=0 の先頭・fpr=tpr=1 の末尾）は残る。
    rng = np.random.default_rng(0)
    y = np.tile(np.array([0, 1], dtype="int64"), 50)
    s = rng.random(100)
    full = ev.roc_table(y, s)
    thin = ev.roc_table(y, s, max_points=5)
    assert len(thin) <= 5 < len(full)
    first, last = thin.to_dicts()[0], thin.to_dicts()[-1]
    assert (first["fpr"], first["tpr"]) == (0.0, 0.0)
    assert (last["fpr"], last["tpr"]) == (1.0, 1.0)


def test_roc_table_single_class_is_error() -> None:
    with pytest.raises(ValueError, match="両方"):
        ev.roc_table(np.array([1, 1, 1], dtype="int64"), np.array([0.2, 0.5, 0.9], dtype="float64"))


def test_roc_table_rejects_max_points_below_two() -> None:
    # max_points<2 は「端点を必ず残す」約束を守れない（1 だと末尾が落ちる）ので拒否する。
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    with pytest.raises(ValueError, match="max_points は 2 以上"):
        ev.roc_table(y, s, max_points=1)


def test_threshold_table_matches_confusion_and_selector() -> None:
    y = np.array([0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.9], dtype="float64")
    tbl = ev.threshold_table(y, s)
    for r in tbl.to_dicts():  # 各行の tp/fp/fn/tn は confusion と一致（土台の共有）
        c = ev.confusion(y, s, threshold=r["threshold"])
        assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (c["tp"], c["fp"], c["fn"], c["tn"])
    best_t, _ = ev.select_threshold_max_f1(y, s)  # f1 最大の行の閾値が選択器と一致
    max_row = max(tbl.to_dicts(), key=lambda r: r["f1"])
    assert max_row["threshold"] == pytest.approx(best_t)


def test_threshold_table_rows_from_construction() -> None:
    # y=[0,0,0,1,1], s=[.1,.4,.6,.6,.9]。明示閾値ごとに pred=(s>=t) を手で数えて tp/fp/fn/tn・P/R/F1 を導出。
    y = np.array([0, 0, 0, 1, 1], dtype="int64")
    s = np.array([0.1, 0.4, 0.6, 0.6, 0.9], dtype="float64")
    tbl = ev.threshold_table(y, s, thresholds=[0.0, 0.5, 0.6, 0.7, 1.0])
    assert tbl.columns == ["threshold", "precision", "recall", "f1", "tn", "fp", "fn", "tp"]  # 列名・順序は不変
    rows = tbl.to_dicts()
    # t=0.0: 全部陽性 → tp=2, fp=3, fn=0, tn=0, P=2/5, R=1, F1=2·(2/5)·1/(2/5+1)=4/7
    assert (rows[0]["tp"], rows[0]["fp"], rows[0]["fn"], rows[0]["tn"]) == (2, 3, 0, 0)
    assert rows[0]["precision"] == pytest.approx(2 / 5)
    assert rows[0]["recall"] == 1.0
    assert rows[0]["f1"] == pytest.approx(4 / 7)
    # t=0.5: pred=[0,0,1,1,1] → tp=2, fp=1, fn=0, tn=2, P=2/3, R=1, F1=4/5
    assert (rows[1]["tp"], rows[1]["fp"], rows[1]["fn"], rows[1]["tn"]) == (2, 1, 0, 2)
    assert rows[1]["precision"] == pytest.approx(2 / 3)
    assert rows[1]["f1"] == pytest.approx(4 / 5)
    # t=0.6: 同値スコアは >= で陽性側 → t=0.5 と同じ数え（境界の包含を固定）。
    assert (rows[2]["tp"], rows[2]["fp"], rows[2]["fn"], rows[2]["tn"]) == (2, 1, 0, 2)
    # t=0.7: pred=[0,0,0,0,1] → tp=1, fp=0, fn=1, tn=3, P=1, R=1/2, F1=2/3
    assert (rows[3]["tp"], rows[3]["fp"], rows[3]["fn"], rows[3]["tn"]) == (1, 0, 1, 3)
    assert rows[3]["recall"] == pytest.approx(1 / 2)
    assert rows[3]["f1"] == pytest.approx(2 / 3)
    # t=1.0: 全部陰性 → tp=fp=0 → P=R=F1=0（0 割しない）。
    assert (rows[4]["tp"], rows[4]["fp"], rows[4]["fn"], rows[4]["tn"]) == (0, 0, 2, 3)
    assert (rows[4]["precision"], rows[4]["recall"], rows[4]["f1"]) == (0.0, 0.0, 0.0)


def test_threshold_table_matches_definition_oracle_on_random_data() -> None:
    # 定義から独立に数える oracle（pred=(s>=t) の集計と P/R/F1 の定義式）と、全行・全列が一致する性質テスト。
    # 期待値は実装出力の写経ではなく、混同行列の定義そのものから導く（ハードコード期待値禁止）。
    rng = np.random.default_rng(42)
    y = (rng.random(200) < 0.3).astype("int64")
    s = rng.random(200)

    def oracle(t: float) -> tuple[int, int, int, int, float, float, float]:
        pred = s >= t
        tp = int(((y == 1) & pred).sum())
        fp = int(((y == 0) & pred).sum())
        fn = int(((y == 1) & ~pred).sum())
        tn = int(((y == 0) & ~pred).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        return tp, fp, fn, tn, p, r, f1

    # 既定スイープ（_curve の閾値）と明示指定の両経路を検査。
    default_tbl = ev.threshold_table(y, s)
    assert len(default_tbl) == len(ev._curve(y, s)[2])  # 行数＝pr 曲線の閾値数（従来と同じ土台）
    explicit_ts = [0.0, 0.25, 0.5, 0.75, 1.0]
    explicit_tbl = ev.threshold_table(y, s, thresholds=explicit_ts)
    assert explicit_tbl["threshold"].to_list() == explicit_ts  # 指定順を保つ
    for tbl in (default_tbl, explicit_tbl):
        for r_ in tbl.to_dicts():
            tp, fp, fn, tn, p, rec, f1 = oracle(r_["threshold"])
            assert (r_["tp"], r_["fp"], r_["fn"], r_["tn"]) == (tp, fp, fn, tn)
            assert r_["precision"] == pytest.approx(p)
            assert r_["recall"] == pytest.approx(rec)
            assert r_["f1"] == pytest.approx(f1)


def test_threshold_table_degenerate_inputs_no_division_error() -> None:
    # 退化：全陽性・全陰性・単一スコア。既定スイープは両クラス必須（_curve）なので明示閾値で通す。0 割しない。
    # 全陽性 y=[1,1], s=[.2,.8], t=.5 → tp=1, fn=1, fp=tn=0 → P=1, R=1/2, F1=2/3。
    all_pos = ev.threshold_table(
        np.array([1, 1], dtype="int64"), np.array([0.2, 0.8], dtype="float64"), thresholds=[0.5]
    ).to_dicts()[0]
    assert (all_pos["tp"], all_pos["fp"], all_pos["fn"], all_pos["tn"]) == (1, 0, 1, 0)
    assert all_pos["precision"] == 1.0
    assert all_pos["recall"] == pytest.approx(1 / 2)
    assert all_pos["f1"] == pytest.approx(2 / 3)
    # 全陰性 y=[0,0] → tp=fn=0（正例なし）→ P=R=F1=0.0（nan にしない）。
    all_neg = ev.threshold_table(
        np.array([0, 0], dtype="int64"), np.array([0.2, 0.8], dtype="float64"), thresholds=[0.5]
    ).to_dicts()[0]
    assert (all_neg["tp"], all_neg["fp"], all_neg["fn"], all_neg["tn"]) == (0, 1, 0, 1)
    assert (all_neg["precision"], all_neg["recall"], all_neg["f1"]) == (0.0, 0.0, 0.0)
    # 単一スコア（全行 0.5）：t=0.5 で全部陽性（>= の境界）・t=0.6 で全部陰性。
    y_one = np.array([0, 1, 0, 1], dtype="int64")
    s_one = np.full(4, 0.5, dtype="float64")
    single = ev.threshold_table(y_one, s_one, thresholds=[0.5, 0.6]).to_dicts()
    assert (single[0]["tp"], single[0]["fp"], single[0]["fn"], single[0]["tn"]) == (2, 2, 0, 0)
    assert single[0]["precision"] == pytest.approx(1 / 2)
    assert single[0]["recall"] == 1.0
    assert (single[1]["tp"], single[1]["fp"], single[1]["fn"], single[1]["tn"]) == (0, 0, 2, 2)
    assert (single[1]["precision"], single[1]["recall"], single[1]["f1"]) == (0.0, 0.0, 0.0)


def test_brier_from_construction() -> None:
    # brier = mean((score - y)²)（brier_score_loss の定義）。期待値はテストデータの構成から厳密に導く。
    # proba=1.0 で y=1（完全確信で正解）→ (1-1)²=0 の平均 = 0（最良）。
    y_all1 = np.array([1, 1, 1, 1], dtype="int64")
    s_sure = np.ones(4, dtype="float64")
    assert ev.evaluate(y_all1, s_sure, metrics=["brier"])["brier"] == 0.0
    # proba=0.5 一律・y 混在 → どの行も (0.5-y)²=0.25 → 平均 0.25（情報ゼロの確率）。
    y_mixed = np.array([0, 1, 0, 1], dtype="int64")
    s_half = np.full(4, 0.5, dtype="float64")
    assert ev.evaluate(y_mixed, s_half, metrics=["brier"])["brier"] == pytest.approx(0.25)
    # 反転（proba=1 で y=0＝完全確信で不正解）→ (1-0)²=1 の平均 = 1（最悪）。
    y_all0 = np.array([0, 0, 0, 0], dtype="int64")
    assert ev.evaluate(y_all0, s_sure, metrics=["brier"])["brier"] == 1.0


def test_brier_registered_direction_and_passes() -> None:
    # カタログ規約：説明文つきで METRICS に載る。向き（小さいほど良い）が passes で効く。
    m = ev.METRICS["brier"]
    assert (m.task, m.input, m.higher_is_better) == ("classification", "score", False)
    assert m.tasks == ("binary",)  # 既定 classification→binary
    assert m.description
    assert ev.passes({"brier": 0.25}, {"brier": 0.3})  # 閾値以下で合格（小さいほど良い）
    assert not ev.passes({"brier": 0.5}, {"brier": 0.3})


# --- T-0080 eval 完成度：bootstrap CI・cost-sensitive 閾値・pinball α ---


def test_bootstrap_ci_deterministic_and_ordered() -> None:
    # 同じ seed → 同じ区間（決定的・rng.choice の再標本のみが乱数源）。lo <= hi は常に成り立つ。
    rng = np.random.default_rng(0)
    y = (rng.random(100) < 0.5).astype("int64")
    s = rng.random(100)
    ci1 = ev.bootstrap_ci(y, s, metric="roc_auc", n_boot=50, seed=7)
    ci2 = ev.bootstrap_ci(y, s, metric="roc_auc", n_boot=50, seed=7)
    assert ci1 == ci2
    lo, hi = ci1
    assert lo <= hi


def test_bootstrap_ci_degenerate_metric_collapses() -> None:
    # pred = y + 1 → どの再標本でも各行の絶対誤差が 1 → mae は常に 1 → 区間は (1, 1) に潰れる（構成から）。
    y = np.arange(10, dtype="float64")
    pred = y + 1.0
    assert ev.bootstrap_ci(y, pred, metric="mae", n_boot=30, seed=0) == (1.0, 1.0)


def test_bootstrap_ci_coverage_near_nominal() -> None:
    # コイン投げ p=0.6・pred 全 1 → accuracy = 標本中の 1 の割合（推定量＝標本平均・真値 p=0.6）。
    # 95% CI が真値を覆う割合はおおむね名目（seed 固定で決定的＝フレーキーにならない）。
    # 下限は 90：正実装は被覆 92 で緑・分位取り違え変異（95%CI のつもりで 90%CI＝
    # np.quantile(stats, [alpha, 1-alpha]) を返す）は被覆 88 で赤にして殺す（85 だと変異が生存する）。
    p = 0.6
    n, trials = 100, 100
    rng = np.random.default_rng(123)
    ones = np.ones(n, dtype="int64")
    covered = 0
    for t in range(trials):
        y = (rng.random(n) < p).astype("int64")
        lo, hi = ev.bootstrap_ci(y, ones, metric="accuracy", n_boot=200, seed=t)
        if lo <= p <= hi:
            covered += 1
    assert covered >= 90


def test_bootstrap_ci_validation() -> None:
    y = np.array([0, 1, 0, 1], dtype="int64")
    s = np.array([0.1, 0.9, 0.2, 0.8], dtype="float64")
    with pytest.raises(ValueError, match="未知の指標"):
        ev.bootstrap_ci(y, s, metric="nope", seed=0)
    with pytest.raises(ValueError, match="alpha"):
        ev.bootstrap_ci(y, s, metric="roc_auc", seed=0, alpha=1.5)
    with pytest.raises(ValueError, match="n_boot"):
        ev.bootstrap_ci(y, s, metric="roc_auc", seed=0, n_boot=0)
    with pytest.raises(ValueError, match="同じ長さ"):
        ev.bootstrap_ci(y, s[:2], metric="roc_auc", seed=0)
    with pytest.raises(ValueError, match="同じ長さ|空"):
        ev.bootstrap_ci(np.array([], dtype="int64"), np.array([], dtype="float64"), metric="roc_auc", seed=0)


def test_select_threshold_min_cost_asymmetric_from_construction() -> None:
    # y=[0,1,0,1], s=[0.2,0.4,0.6,0.8]。閾値の区分ごとの (fp, fn)（pred = score >= t）：
    #   t<=0.2 全陽性 (2,0)／(0.2,0.4] (1,0)／(0.4,0.6] (1,1)／(0.6,0.8] (0,1)／t>0.8 全陰性 (0,2)
    # fp_cost=1, fn_cost=10 → 費用 [2,1,11,10,20] → 最小は t=0.4・費用 1（見逃しが高価→広めに拾う）。
    y = np.array([0, 1, 0, 1], dtype="int64")
    s = np.array([0.2, 0.4, 0.6, 0.8], dtype="float64")
    assert ev.select_threshold_min_cost(y, s, fp_cost=1.0, fn_cost=10.0) == (0.4, 1.0)
    # 費用を逆転（fp_cost=10, fn_cost=1）→ 費用 [20,10,11,1,2] → 最小は t=0.8・費用 1（誤検知が高価→狭める）。
    assert ev.select_threshold_min_cost(y, s, fp_cost=10.0, fn_cost=1.0) == (0.8, 1.0)


def test_select_threshold_min_cost_all_negative_optimum() -> None:
    # 正例のスコアが最下位（y=[1,0,0], s=[0.5,0.6,0.7]）・誤検知が高価（fp=100, fn=1）：
    #   t=0.5 (2,0)=200／t=0.6 (2,1)=201／t=0.7 (1,1)=101／全陰性 (0,1)=1 → 全陰性（max スコア直上）が最適。
    y = np.array([1, 0, 0], dtype="int64")
    s = np.array([0.5, 0.6, 0.7], dtype="float64")
    t, cost = ev.select_threshold_min_cost(y, s, fp_cost=100.0, fn_cost=1.0)
    assert t > 0.7
    assert cost == 1.0
    # 返した閾値はそのまま confusion に渡せる（>= 判定が同じ）＝数えの同値性。
    c = ev.confusion(y, s, threshold=t)
    assert cost == c["fp"] * 100.0 + c["fn"] * 1.0


def test_select_threshold_min_cost_tie_prefers_larger() -> None:
    # y=[1,0], s=[0.3,0.7]・等費用：t=0.3 (1,0)=1／t=0.7 (1,1)=2／全陰性 (0,1)=1
    # → 同点（費用 1）は大きい方の閾値（max_f1 と同じ規約）＝全陰性側（> 0.7）。
    y = np.array([1, 0], dtype="int64")
    s = np.array([0.3, 0.7], dtype="float64")
    t, cost = ev.select_threshold_min_cost(y, s, fp_cost=1.0, fn_cost=1.0)
    assert t > 0.7
    assert cost == 1.0


def test_select_threshold_min_cost_validation() -> None:
    y = np.array([0, 1], dtype="int64")
    s = np.array([0.2, 0.8], dtype="float64")
    with pytest.raises(ValueError, match="正"):
        ev.select_threshold_min_cost(y, s, fp_cost=0.0, fn_cost=1.0)
    with pytest.raises(ValueError, match="正"):
        ev.select_threshold_min_cost(y, s, fp_cost=1.0, fn_cost=-1.0)
    # 単一クラスは兄弟（select_threshold_*）と同じく _curve が止める。
    with pytest.raises(ValueError, match="正例・負例"):
        ev.select_threshold_min_cost(np.array([1, 1], dtype="int64"), s, fp_cost=1.0, fn_cost=1.0)


def test_pinball_alpha_asymmetry_from_definition() -> None:
    # 定義：loss = α·max(y−pred, 0) + (1−α)·max(pred−y, 0)。
    # 過小予測（y=1, pred=0）→ α×1。過大予測（y=0, pred=1）→ (1−α)×1（符号で非対称が出る）。
    y_under = np.array([1.0], dtype="float64")
    p_under = np.array([0.0], dtype="float64")
    assert ev.pinball(y_under, p_under, alpha=0.1) == pytest.approx(0.1)
    assert ev.pinball(y_under, p_under, alpha=0.9) == pytest.approx(0.9)
    y_over = np.array([0.0], dtype="float64")
    p_over = np.array([1.0], dtype="float64")
    assert ev.pinball(y_over, p_over, alpha=0.1) == pytest.approx(0.9)
    assert ev.pinball(y_over, p_over, alpha=0.9) == pytest.approx(0.1)


def test_pinball_alpha_half_is_half_mae_and_default() -> None:
    # α=0.5 は |誤差|/2 の平均＝mae/2。y=[0,0], pred=[3,4] → mae=3.5 → 1.75。既定引数も α=0.5。
    y = np.array([0.0, 0.0], dtype="float64")
    p = np.array([3.0, 4.0], dtype="float64")
    assert ev.pinball(y, p, alpha=0.5) == pytest.approx(1.75)
    assert ev.pinball(y, p) == pytest.approx(1.75)


def test_pinball_alpha_validation() -> None:
    y = np.array([0.0], dtype="float64")
    p = np.array([1.0], dtype="float64")
    for bad in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError, match="alpha"):
            ev.pinball(y, p, alpha=bad)


def test_pinball_quantile_metrics_registered_and_evaluated() -> None:
    # ：代表分位（q10/q90）が説明文つきで METRICS に載り、evaluate_regression から名前で引ける。
    for name in ("pinball_q10", "pinball_q90"):
        m = ev.METRICS[name]
        assert m.description
        assert m.tasks == ("regression",)
        assert m.higher_is_better is False
        assert m.input == "value"
    # y=[1], pred=[0]（過小予測 1）→ q10=0.1・q50（pinball）=0.5・q90=0.9（定義から）。
    y = np.array([1.0], dtype="float64")
    p = np.array([0.0], dtype="float64")
    out = ev.evaluate_regression(y, p, metrics=["pinball_q10", "pinball", "pinball_q90"])
    assert out["pinball_q10"] == pytest.approx(0.1)
    assert out["pinball"] == pytest.approx(0.5)
    assert out["pinball_q90"] == pytest.approx(0.9)
