---
id: T-0080
kind: task
status: done
title: eval 完成度（bootstrap CI・cost-sensitive 閾値・pinball α）
created: 2026-07-06
depends_on: [T-0076]
verified_by:
  - tests/test_ds_eval.py::test_bootstrap_ci_coverage_near_nominal
  - tests/test_ds_eval.py::test_select_threshold_min_cost_asymmetric_from_construction
  - tests/test_ds_eval.py::test_pinball_alpha_asymmetry_from_definition
  - tests/test_ds_eval.py::test_pinball_quantile_metrics_registered_and_evaluated
---
# T-0080 eval 完成度

## 背景（次点部品・sklearn/scipy 素通し・DEC-0006/0010）
- **bootstrap CI**：leaderboard の変種差が「ノイズか本物か」を判定する道具が無い。OOF 指標の信頼区間を足す。
- **cost-sensitive 閾値**：実務で最頻の閾値要求（誤検知/見逃しの費用が非対称）。既存 `select_threshold_*` 兄弟の横に。
  T-0076 の累積 tp/fp 土台に相乗りできる。
- **pinball α**：分位点回帰の評価に α（分位）を渡せるように（既存 pinball を α 引数化・quantile 変種を METRICS に）。

## 受け入れ基準（sklearn/scipy 素通し・DEC-0009 入口まで）
- `bootstrap_ci(y_true, y_score, *, metric, n_boot, seed, alpha=0.05)`：rng.choice 再標本＋METRICS 委譲で (lo, hi)（または小 struct）。
  seed 明示・決定的。docstring に使い方。
- `select_threshold_min_cost(y_true, y_score, *, fp_cost, fn_cost)`：期待費用最小の閾値（既存 select_threshold_* と同じ署名・
  累積カウント土台）。docstring。
- pinball を α 引数対応にし、代表分位（例 0.1/0.5/0.9）を METRICS に登録（`data metrics` カタログに載る・向き＝小が良い）。
- **DEC-0009**：METRICS 追加分は description つきでカタログ掲載（test_catalog が守る）。関数は docstring で「何を・どう呼ぶ」。

## 触ってよいファイル
`src/harness/ds/eval.py`＋`tests/test_ds_eval.py`（必要なら test_catalog）。`pipeline.py`/`eda.py`/`cv.py`/`experiment.py`/`analysis.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- bootstrap_ci：既知分布（コイン投げ等）で被覆率がおおむね名目・seed 固定で決定的。
- select_threshold_min_cost：費用が非対称な合成データで最適閾値が解析解と一致（構成から導出）。
- pinball α：α=0.5 が MAE/2 に一致等・分位の非対称性が符号に出る。METRICS カタログ掲載。

## 独立レビュー（maker≠checker・差分のみ・実測）
実装欠陥なし。bootstrap_ci は独立 300 試行で被覆率 95.3%（名目 95）・恒等 mae で区間 (1,1)・決定的。min_cost は素朴総当たりと 500 試行で
完全一致・番兵/同点規約/confusion 費用同値を確認。pinball α は sklearn と 1e-12 一致・α=0.5=MAE/2・quantile 指標カタログ掲載。
変異 5/6 撃墜、生存した被覆率テストの緩さ（下限 85→分位取り違え変異が 88 で通過）を下限 90 に締め決定的に撃墜。
