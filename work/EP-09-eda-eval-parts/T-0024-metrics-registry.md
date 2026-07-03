---
id: T-0024
kind: task
status: done
title: 評価指標レジストリ（METRICS・向き付き）と data metrics
depends_on: [EP-09]
created: 2026-07-03
verified_by:
  - tests/test_ds_eval.py::test_metrics_registry_covers_classification_and_regression
  - tests/test_ds_eval.py::test_passes_respects_direction_and_rejects_unknown
  - tests/test_catalog.py::test_metrics_have_descriptions
---
# T-0024 評価指標レジストリの背骨

## 受け入れ基準
- `eval.METRICS`（分類 roc_auc/pr_auc/log_loss/accuracy/f1/precision/recall・回帰 rmse/mae/mape）が向き付きで登録され、
  本体は sklearn.metrics 素通し。`evaluate`（分類・選択可）・`evaluate_regression`・`metric_fn_for(task)`。
- `passes` はレジストリの向きで `>=`/`<=` を切り替え、未登録の閾値名は ValueError。
- 縁の吸収：log_loss は labels=[0,1]、pr_auc は単一クラスで方針値。
- 入口：`uv run data metrics`＋test_catalog に説明文必須検査。E-0001 は無変更で緑（additive）。

## 結果
実装・独立レビュー・verify 緑・DESIGN §5 手順1 完了。歩く骨組みの背骨（レジストリ→config 語彙→CLI 一覧→機械検査）が一巡。
