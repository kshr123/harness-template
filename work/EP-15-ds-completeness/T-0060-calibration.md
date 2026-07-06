---
id: T-0060
kind: task
status: done
title: 確率較正（CalibratedClassifierCV を model に被せる）＋brier 指標
created: 2026-07-06
depends_on: [T-0057]
verified_by:
  - tests/test_ds_eval.py::test_brier_from_construction
  - tests/test_ds_eval.py::test_brier_registered_direction_and_passes
  - tests/test_ds_pipeline.py::test_build_model_with_calibrate_wraps_and_wires_seed
  - tests/test_ds_pipeline.py::test_build_model_calibrate_defaults
  - tests/test_ds_pipeline.py::test_build_model_without_calibrate_is_unchanged
  - tests/test_ds_pipeline.py::test_build_model_tune_then_calibrate_order
  - tests/test_ds_pipeline.py::test_calibrate_unknown_key_fails_loud
  - tests/test_ds_pipeline.py::test_calibrate_on_regression_model_rejected_at_config
  - tests/test_ds_pipeline.py::test_calibrated_model_runs_through_run_cv
---
# T-0060 確率較正＋brier

## 背景
分類の予測確率は較正されていないことが多い（log_loss/閾値判断が歪む）。sklearn の CalibratedClassifierCV を
「model に被せる」継ぎ目（tune と同じ流儀）で足し、較正のずれを測る brier を指標に足す。参考リポの calibration 比較に相当。

## 受け入れ基準（sklearn 素通し・DEC-0006）
- `pipeline.py`：`build_model` の spec に `calibrate:` があれば built model を `CalibratedClassifierCV` で包む
  （`calibrate: {method: "sigmoid"|"isotonic"(既定 sigmoid), cv: 3}`）。内側 cv は seed 付き
  `StratifiedKFold(shuffle=True, random_state=seed)`。model 段に置くので run_cv の clone-per-fold でそのまま
  fold の train で較正＝リークなし。`calibrate` キーが無ければ**従来不変**。tune と併用時は tuned を包む（or 明示順）。
  実装は tune の build_tuned と同じ薄さ（別関数 `build_calibrated` にしてよい・循環 import 注意）。
- `eval.py`：`brier`（`brier_score_loss`・classification・score・higher_is_better=False・小さいほど良い）を METRICS に追加
  （既存の `_register_metric` 流儀・sklearn 素通し）。カタログに description つきで載る（DEC-0009）。

## 触ってよいファイル
`src/harness/ds/pipeline.py`（build_model の calibrate 配線＋factory）・`src/harness/ds/eval.py`（brier 登録）・
`tests/test_ds_pipeline.py`・`tests/test_ds_eval.py`。`models.py`/`cv.py`/`tune.py`/`features.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- `calibrate` 付き build_model が `CalibratedClassifierCV` を返し、内側 cv が seed 付き（決定的）。無しは従来の素の model（型で確認）。
- 較正モデルを `run_cv` に通すと fit/predict が通り `cv._predict` が proba を返す（nested・二値）。
- brier：完全確信で正解（proba=1 で y=1）なら 0、proba=0.5 一律なら 0.25（(0.5-y)²の平均＝構成から厳密）。
- brier がカタログ（data metrics）に載る・向き（小さいほど良い）が passes で効く。

## 独立レビュー（2026-07-06・maker≠checker）
較正リーク無し（内側較正 cv が外側 train だけで回る）・決定性・cv._predict 委譲・brier の退化 fold 耐性を実測で確認。
important 1：calibrate 節の未知キーが黙って捨てられ typo が fail-open（metod→sigmoid に化ける）＝build_tuned と非対称
→ method/cv 以外を CalibratedClassifierCV へ素通しし、未知キーは TypeError で即死（fail-loud）。minor：回帰モデル×calibrate
を config 段で ValueError に（fit を待たず「calibrate は分類のみ」）。回帰テスト 2 本追加。

## 結果
実装・独立レビュー（未知キーの fail-loud 化・回帰ガードを反映）・verify 緑で done。参考リポ calibration＝ideal-build-plan Wave 3。
