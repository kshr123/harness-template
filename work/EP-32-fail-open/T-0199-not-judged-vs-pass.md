---
id: T-0199
kind: task
status: done
title: "「判定 0 件」を合格と区別する（passed は bool | None）・初回昇格の緩和を明示する"
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0197]
verified_by:
  - tests/test_ds_experiment.py::test_run_experiment_without_thresholds_is_not_judged_not_passed
  - tests/test_gates.py::test_evaluate_zero_specs_is_approved_but_not_judged
  - tests/test_gates.py::test_evaluate_first_promotion_is_named_when_no_baseline
---
# T-0199 判定していないと合格を区別する

## 何が問題か
`passes(x, {})` は判定 0 件で `all([])=True`＝合格を返す（探索では正当）。だが `run_experiment` はこれを
そのまま `ExperimentResult.passed: bool` に入れていたので、**閾値を 1 つも宣言していない実験が passed=True**に
なった（`final_eval_on_holdout` は `thresholds is None → passed=None` と正しく区別していたのに、非対称）。
「判定していない」が「合格」と同じ値で表れるのは、黙って通る経路。

初回昇格（champion が無い）では改善量を問えないので `change_threshold` が緩和される（no_baseline）。これは
設計どおりだが**暗黙**だった。

## やったこと（一律 ValueError にはしない）
探索（指標だけ見る）は正当な使い方なので `gates.evaluate` の空 specs を ValueError にはしない（それは
EP-32 で却下済み）。代わりに**区別できる型**にした：
- `ExperimentResult.passed: bool | None`。`run_experiment` は閾値が空なら `None`（未判定）を入れる
  （`final_eval_on_holdout` と同じ流儀）。`train.py` は passed=None を成功（exit 0）にしない。
- `PromotionDecision.judged`（1 件でも判定したか）と `first_promotion`（no_baseline の緩和が効いたか）を
  property で足す。approved（`all([])=True`）と別に「判定していない」「初回の緩和」を名指しできる。
  promote 経路は必ず change_threshold を含むので judged=True。空になりうるのは探索の passes 側だけ。

## 受け入れ基準
- 閾値なしの `run_experiment` は `passed is None`（True でも False でもない）。指標は出る。
- `evaluate(ctx, [])` は `approved=True` かつ `judged=False`。初回昇格は `first_promotion=True`。
- `uv run verify` 全成功。
