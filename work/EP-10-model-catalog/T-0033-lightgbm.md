---
id: T-0033
kind: task
status: done
title: LightGBM を optional extra ＋条件登録（未導入ヒント）＋numpy 境界
depends_on: [T-0031]
created: 2026-07-03
verified_by:
  - tests/test_ds_models_lightgbm.py::test_unknown_kind_hint_with_monkeypatched_absence
  - tests/test_ds_models_lightgbm.py::test_lightgbm_registered_and_runs
---
# T-0033 LightGBM（T-C）

## 受け入れ基準
- pyproject に optional extra `lightgbm`＋mypy override。pipeline.py に `_lightgbm`/`_lightgbm_reg`＋find_spec 条件登録
  （入っていれば MODELS に載る・`data models` に表示）。未導入 kind のエラーに `uv sync --extra lightgbm` ヒント。
- AGENTS の DS 節に「開発・verify は `uv sync --all-extras`」規約（optional 依存を skip しない）。
- テスト：未導入は monkeypatch で再現・導入済みは 11 kind で proba 経路に載る。

## 併せて直した設計上の穴（build_estimator）
- FeaturePipeline は polars を出力し、2段（encode 無し）では model が polars を受ける。logreg は許容するが LightGBM は
  `feature_names_in_` を設定できず落ちる。**DESIGN の「numpy 境界は1点」を実装**＝model 直前に `_to_numpy`（FunctionTransformer・
  one-to-one）を差し込み、全モデルで名前付き入力に依存せず動くようにした。既存 e2e/実験は指標不変で緑。
- 既知の無害な warning：sklearn が one-to-one の名前を LGBM に伝えるため predict 時に「feature names 不一致」の UserWarning
  が出る（予測は正常・verify 緑）。実害なし。

## 結果
実装・verify 緑。data models は all-extras 環境で 12 kind（分類 6・回帰 6）。
