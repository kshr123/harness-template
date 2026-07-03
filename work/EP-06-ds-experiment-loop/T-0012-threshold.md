---
id: T-0012
kind: task
status: done
title: 閾値選択 select_threshold_*（eval・sklearn.metrics・OOF で選ぶ）
requirements: [REQ-004]
depends_on: [T-0014]
verified_by:
  - tests/test_ds_eval.py::test_select_threshold_max_f1_exact
  - tests/test_ds_eval.py::test_select_threshold_at_recall
  - tests/test_ds_eval.py::test_select_threshold_single_class_is_error
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0012 閾値選択（eval.py 追記）

## 目的
分類の決定境界（閾値）を valid/OOF の予測から選ぶ部品。train/test では選ばない（過大評価・漏れの防止）。
実装は sklearn.metrics（precision_recall_curve/f1_score）へ委譲（再発明しない・DEC-0006）。設計は DESIGN.md B-1。

## 受け入れ基準（テスト先行で）
- `select_threshold_max_f1(y_true,y_score)→(閾値,F1)`／`select_threshold_at_recall(...,*,target)`／`select_threshold_at_precision(...,*,target)`。
- 規約「閾値は valid/OOF で選ぶ」を docstring に明記。返り値は evaluate にそのまま渡せる（>= 判定一致）。
- 単一クラスは失敗。単体テストは構成から厳密（0.6/F1=1.0・同点は大きい方）。
- train.py が OOF から閾値を選び results に記録（一気通貫に接続）。
- `uv run verify` 全成功。
