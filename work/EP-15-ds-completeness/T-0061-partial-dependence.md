---
id: T-0061
kind: task
status: done
title: 部分依存表（partial_dependence_table）＝入力列を振って平均予測の形を見る
created: 2026-07-06
depends_on: [T-0053]
verified_by:
  - tests/test_ds_analysis.py::test_partial_dependence_monotone_increasing_with_logreg
  - tests/test_ds_analysis.py::test_partial_dependence_grid_passthrough_sorted
  - tests/test_ds_analysis.py::test_partial_dependence_n_points_linspace
  - tests/test_ds_analysis.py::test_partial_dependence_discrete_uses_unique_values
  - tests/test_ds_analysis.py::test_partial_dependence_keeps_other_columns
  - tests/test_ds_analysis.py::test_partial_dependence_int_feature_with_join_encoder
  - tests/test_ds_analysis.py::test_partial_dependence_rejects_multiclass_proba
---
# T-0061 部分依存表（PDP）

## 背景
permutation_importance（既存・analysis.py）は「どの列が効くか」を測るが「どう効くか（形）」は分からない。
入力列をグリッドで振って平均予測を見る部分依存表を足す（説明可能性の残り＝ideal-build-plan Wave 3「PDP」）。
SHAP は heavy な optional なので本タスクでは扱わない（別途 extra・ISS 化してよい）。

## 受け入れ基準（polars ネイティブ・既存 permutation_importance と同じ流儀＝DEC-0008）
- `analysis.py` に `partial_dependence_table(estimator, x, feature, *, grid=None, n_points=20, predict="proba",
  threshold は不要) -> pl.DataFrame`（列 = feature_value, avg_prediction）。
  - grid 未指定：数値列は min..max を n_points 等分、少数のユニーク値（カテゴリ/離散）はユニーク値そのもの
    （polars で判定）。grid 指定時はその値で振る。
  - 各グリッド値 v について、x の `feature` 列を全行 v に置換した DataFrame で `_predict`（既存の analysis._predict 素通し・
    proba は陽性確率）→ 平均を avg_prediction に。ICE 平均の PDP（学習済み Pipeline 丸ごと・モデル非依存）。
  - x は fit に使っていない行（fold の valid / holdout）で呼ぶ（docstring に明記＝permutation_importance と同じ規律）。
- 既存の analysis 関数・permutation_importance は不変。sklearn.inspection.partial_dependence を使わない理由は
  permutation_importance と同文（polars 入力・MultiHot の list 列に入らない＝DEC-0008）を docstring に。

## 触ってよいファイル
`src/harness/ds/analysis.py`＋`tests/test_ds_analysis.py`。`pipeline.py`/`eval.py`/`models.py`/`cv.py` は触らない（並行作業あり・eval は import 可）。

## 検査（テスト先書き・構成から導く）
- 単調な関係を仕込む：`feature` が大きいほど陽性になる学習済みモデル（線形分離データで logreg を fit）で、
  avg_prediction が feature_value について単調増加（構成から導ける向き）。
- grid 指定でその値だけの行が返る・n_points で数値グリッドの行数が決まる。
- 離散列（少数ユニーク）はユニーク値がグリッドになる。
- feature 列を置換しても他列は保たれる（平均予測は置換列だけの効果）。

## 独立レビュー（2026-07-06・maker≠checker）
置換の正当性・グリッド分岐・単調性テストの構成由来を実測で確認。important 2 件を反映：(1) `pl.lit(v)` が Int64 の離散
feature を Float64 に化かし CountEncode 等 join 系エンコーダが SchemaError（f64 vs i64）→ `pl.lit(v).cast(元 dtype)` で
dtype 保持。(2) 多クラス proba が np.mean で 1/k に潰れて黙って誤る → `pred.ndim != 1` を検出して fail-closed
（二値/回帰向けと docstring 明示）。回帰テスト 2 本（Int64×join エンコーダ・多クラス拒否）追加。

## 結果
実装・独立レビュー（dtype 保持・多クラス fail-closed を反映）・verify 緑で done。ideal-build-plan Wave 3「説明可能性」。
