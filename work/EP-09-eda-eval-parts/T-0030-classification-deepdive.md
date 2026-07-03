---
id: T-0030
kind: task
status: done
title: 分類予測の深掘り（混同行列・クラス別指標・較正・閾値スイープ）
depends_on: [T-0024]
created: 2026-07-03
verified_by:
  - tests/test_ds_eval.py::test_confusion_from_construction
  - tests/test_ds_eval.py::test_class_metrics_both_classes
  - tests/test_ds_eval.py::test_calibration_table_single_bin
  - tests/test_ds_eval.py::test_threshold_table_matches_confusion_and_selector
---
# T-0030 分類予測の深掘り（DESIGN §9-2）

## 受け入れ基準
- `eval`：confusion（{tn,fp,fn,tp}・confusion_matrix labels=[0,1]）／class_metrics（両クラスの precision/recall/f1・
  precision_recall_fscore_support 素通し）／calibration_table（較正表＋件数・quantile はデシル表兼用）／
  threshold_table（閾値スイープ・行は confusion 再利用・閾値選択は select_threshold_* と重複させない）。
- すべて y_true/y_score の純関数（CLI なし・experiment スキル「結果の深掘り」節が導線・OOF で呼ぶ）。
- 期待値は構成から導出（tn=fp=fn=tp==1・両クラス 0.5・1 ビン fraction 0.25・threshold 行 == confusion）。

## 結果
実装・verify 緑・DESIGN §9-2 完了。分類の深掘り（何を間違え・どちらが弱く・確率は信じられ・境界を動かすと）が部品化。
