---
id: T-0053
kind: task
status: done
title: 指標追加（r2/mcc/balanced_accuracy/pinball）＋calibration 診断＋roc_table
created: 2026-07-06
depends_on: [T-0051]
verified_by:
  - tests/test_ds_eval.py::test_r2_from_construction
  - tests/test_ds_eval.py::test_pinball_is_half_mae_at_default_alpha
  - tests/test_ds_eval.py::test_mcc_and_balanced_accuracy_binary_from_construction
  - tests/test_ds_eval.py::test_mcc_and_balanced_accuracy_multiclass_perfect
  - tests/test_ds_eval.py::test_calibration_zero_when_means_match_and_grows_when_overpredicting
  - tests/test_ds_eval.py::test_calibration_nan_when_no_positives
  - tests/test_ds_eval.py::test_roc_table_perfect_separation
  - tests/test_ds_eval.py::test_roc_table_max_points_thins_keeping_ends
  - tests/test_ds_eval.py::test_roc_table_rejects_max_points_below_two
  - tests/test_ds_eval.py::test_new_metrics_registry_vocabulary
---
# T-0053 指標追加＋診断表

## 受け入れ基準
- METRICS に sklearn 素通しで追加（DEC-0006・手書き禁止）：
  - `r2`（`r2_score`・regression・value・higher_is_better=True）
  - `pinball`（`mean_pinball_loss` alpha=0.5・regression・value・小さいほど良い。docstring に「分位回帰向け・既定 α=0.5」）
  - `mcc`（`matthews_corrcoef`・分類・label・tasks=("binary","multiclass")・higher_is_better=True）
  - `balanced_accuracy`（`balanced_accuracy_score`・分類・label・tasks=("binary","multiclass")・higher_is_better=True）
  - `calibration`（診断＝mean(score)/mean(true)。参考リポの calibration に相当。score・higher_is_better は「1 に近いほど良い」
    ため単純な向きに乗らない＝**閾値の向き属性を持たせず診断専用**にするか、`abs(1-ratio)` を小さいほど良いにするか、
    実装時に無理のない形を選ぶ。カタログには載せる＝description 必須）。
- `roc_table(y_true, y_score, *, max_points=None) -> pl.DataFrame`（列 = fpr, tpr, threshold）を追加。`sklearn.metrics.roc_curve`
  素通し（calibration_table と同じ構造化表の流儀・人は marimo で見る）。点数が多いとき max_points で間引く口（任意）。
- 既存指標・評価関数の挙動は不変。多クラス（T-0051）の mcc/balanced_accuracy は evaluate_multiclass の既定集合にも自動で載る。

## 触ってよいファイル
`src/harness/ds/eval.py`＋`tests/test_ds_eval.py`（＋必要なら `tests/test_catalog.py` に新指標の説明文検査を足す）。
それ以外（cli.py・pipeline.py 等）は触らない。カタログの tasks 列表示（多クラスレビュー IS-5）は CLI タスクで別途。

## 検査（テスト先書き・構成から導く）
- r2：完全一致予測で 1.0、平均予測（説明力ゼロ）で 0.0（構成から）。
- mcc/balanced_accuracy：完全一致で 1.0、二値で全部外すと mcc=-1.0（構成から）。多クラスでも完全一致 1.0。
- calibration：mean(score)=mean(true) の構成で 1.0（または差 0）。過大予測で >1（または正の差）。
- roc_table：単調な tpr/fpr（0→1）・閾値降順、完全分離データで AUC 相当の角（tpr=1,fpr=0 の点が出る）を構成から確認。

## 独立レビュー（2026-07-06・maker≠checker）
blocking なし。important 1（pinball の説明「既定 α=0.5」が変更可能と誤読される＋点予測では mae/2）→ 説明を
「α=0.5 固定・点予測では mae/2・分位回帰導入時に α の口を足す」に是正。minor：`calibration`→`calibration_gap` に改名
（reliability の calibration_table と紛らわしい）・roc_table の `max_points<2` を拒否（端点を残す約束を守れないため）。
据え置き：mcc/BA が退化 fold で sklearn UserWarning（passes は OOF 判定で実害なし）・カタログの tasks 列非表示
（CLI タスクで対応予定＝多クラスレビュー IS-5 と同件）。

## 結果
実装・独立レビュー（反映）・verify 緑で done。参考リポ calibration/roc 取り込み＝ideal-build-plan Wave 3・§参考。
