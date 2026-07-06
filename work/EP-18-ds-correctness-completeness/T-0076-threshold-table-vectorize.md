---
id: T-0076
kind: task
status: done
title: threshold_table を sklearn 曲線委譲＋累積カウントでベクトル化（O(n²) 解消・DEC-0006）
created: 2026-07-06
depends_on: []
verified_by:
  - tests/test_ds_eval.py::test_threshold_table_rows_from_construction
  - tests/test_ds_eval.py::test_threshold_table_matches_definition_oracle_on_random_data
  - tests/test_ds_eval.py::test_threshold_table_degenerate_inputs_no_division_error
---
# T-0076 threshold_table ベクトル化

## 背景（G3）
`eval.threshold_table`（L562 付近）は既定スイープが「全ユニーク閾値 × 毎回 full `confusion_matrix`」＝O(n²)。
P/R/F1 も手書きで、`_curve`（sklearn 出力）と二重＝DEC-0006（再発明しない）違反の残り。

## 受け入れ基準（sklearn 素通し・出力不変）
- ソート済みスコアの累積和で tp/fp/fn をベクトル化（1 パス）。P/R/F1 は sklearn の
  `precision_recall_curve`（または累積カウントから直接）で導出＝手書き除去。
- **公開 API・列・既存テストの期待値は不変**（純粋な内部最適化。行数・列名・値が現行と一致）。
- 既定スイープと明示 thresholds 指定の両経路を維持。

## 触ってよいファイル
`src/harness/ds/eval.py`（threshold_table と補助のみ）＋`tests/test_ds_eval.py`。
`pipeline.py`/`cv.py`/`models.py`/`eda.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 小データ（陽性/陰性の構成が既知）で、新実装の全行が現行実装と一致するプロパティ/回帰テスト（金メッキでなく構成から
  tp/fp/P/R/F1 を導出して照合）。
- 既存 threshold_table テストが不変で緑。
- 退化（全陽性・全陰性・単一スコア）で 0 割せず妥当。

## 独立レビュー（maker≠checker・差分のみ・実測）
重大欠陥なし。旧実装を写経復元し、乱数 20 シード・同値スコア・退化ケースで全列ビット一致を実測（境界 score==t は
searchsorted side="left" で旧 >=t と一致）。独立オラクルとも全行一致。変異 5/5 撃墜（テスト金メッキなし）。DEC-0006 の手書き
除去も確認。注記 2 件は契約外入力（float32 明示閾値・NaN スコア。署名は float64・既定スイープ経路は一致確認済み）で修正不要と
判断。verify 全体緑で done。
