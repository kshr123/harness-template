---
id: T-0074
kind: task
status: done
title: pipeline 正しさ（TargetEncoder 分類層化・回帰 tune 内側 CV・mutual_info_regression）
created: 2026-07-06
depends_on: [T-0057, T-0064]
verified_by:
  - tests/test_ds_pipeline.py::test_target_encoder_cv_is_stratified_for_classification
  - tests/test_ds_pipeline.py::test_target_encoder_classification_inner_folds_keep_class_ratio
  - tests/test_ds_pipeline.py::test_target_encoder_unknown_task_fails_loud
  - tests/test_ds_pipeline.py::test_selectkbest_mutual_info_regression_registered_and_seeded
  - tests/test_ds_tune.py::test_build_tuned_regression_uses_kfold_inner_cv
  - tests/test_ds_tune.py::test_regression_tune_runs_through_run_cv
---
# T-0074 pipeline 正しさ

## 背景（3 面 fable 調査 G2/G8/G9）
- **G2**：`pipeline._target` の `TargetEncoder(cv=KFold(seed))` が分類でも**非層化**。sklearn 既定（cv=int）は分類なら
  内部 StratifiedKFold なのに、決定化のために層化を捨て、不均衡データで内側エンコーディングが静かに劣化する。
- **G8**：`tune.build_tuned` の内側 CV が常に `StratifiedKFold`＝回帰モデル＋`tune:` は fit 時に "continuous label" で落ちる。
  回帰モデルが 5 種登録済みなのに継ぎ目が半分死んでいる。
- **G9**：`pipeline._SCORE_FUNCS` に `mutual_info_regression` が無く、回帰の MI 特徴選択が config から選べない。

## 受け入れ基準（sklearn 素通し・決定性維持・DEC-0006）
- TargetEncoder：分類 task では `StratifiedKFold(shuffle=True, random_state=seed)`、回帰では従来の KFold(seed)。task は
  encode/build_estimator が model 経由で知り得る配線で渡す（既存の task 語彙 binary|multiclass|regression に整合）。決定性は
  seed 明示で維持（グローバル種禁止）。
- 回帰 tune：`build_tuned` の内側 CV を task で分岐（回帰＝KFold(seed)・分類＝StratifiedKFold(seed)）。ridge 等＋`tune:` の
  run_cv が緑になる。
- `mutual_info_regression` を score_func 文字列に登録（既存 f_regression の隣）。seed 決定化。
- 3 つとも `data encoders`/`data selectors` 等のカタログ掲載・docstring は既存の書き方に合わせる（DEC-0009）。

## 触ってよいファイル
`src/harness/ds/pipeline.py`・`src/harness/ds/tune.py`＋`tests/test_ds_pipeline.py`・`tests/test_ds_tune.py`。
`eval.py`/`eda.py`/`unsupervised.py`/`models.py`/`cli.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 不均衡合成データ（陽性 20% 等）で分類 TargetEncoder の内側各 fold の陽性率がクラス比を保つ（非層化より分散が小さい／
  層化 KFold の分割と一致）。回帰では従来どおり。seed 固定で 2 回同一。
- 回帰モデル（ridge/hist_gb_reg 等）＋`tune:` を run_cv に通して fit/predict が通る（pre-fix では失敗する赤テストを先に）。
- selectkbest(score_func=mutual_info_regression) が回帰データで登録・fit・seed 決定化。

## 独立レビュー（maker≠checker・差分のみ・実測）
実装欠陥なし。8 通りのラップ形態（plain・Pipeline 包み・RandomizedSearchCV・CalibratedClassifierCV）で is_classifier 配線が
正しく分類→StratifiedKFold／回帰→KFold（shuffle=True, random_state=seed）を選ぶことを実測。不均衡 100 行で内側 fold の陽性率が
厳密に 0.2（層化）・同 seed で OOF 一致・異 seed で不一致。回帰 tune は旧実装（StratifiedKFold 固定）に戻すと "continuous" で死に、
新テストが赤＝修正が効く証拠。変異 A〜D すべて赤。T-0020 の verified_by は骨抜きでない（回帰側検査＋分類側新テスト＋既存 OOF 生存
テストで担保）。指摘 1（軽微）：G9 の seed 決定性検査が確率的（~40% で変異見逃し）→ partial.keywords の構造 assert に修正、
変異が 1 回で確実に赤になることを再確認。verify 全体緑で done。
