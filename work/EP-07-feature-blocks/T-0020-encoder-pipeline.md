---
id: T-0020
kind: task
status: done
title: sklearn エンコーダを用意する pipeline.py（ENCODERS＋build_estimator・3段Pipeline）
requirements: [REQ-004]
depends_on: [T-0019]
verified_by:
  - tests/test_ds_pipeline.py::test_build_estimator_assembles_three_and_two_stages
  - tests/test_ds_pipeline.py::test_onehot_safe_default_and_override
  - tests/test_ds_pipeline.py::test_target_encoder_cv_is_seeded_kfold
  - tests/test_ds_pipeline_integration.py::test_unseen_category_does_not_crash_and_learns_on_train_fold
  - tests/test_ds_pipeline_integration.py::test_bins_and_pca_handle_null_through_cv
  - tests/test_ds_pipeline_integration.py::test_target_encoder_inner_oof_is_alive_and_deterministic
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0020 sklearn エンコーダを用意する pipeline.py

## 目的
「sklearn を直接使う（作らない・DEC-0008）」を、**必要なときに確実に使える**形で用意する。config 駆動で
特徴量→エンコード→モデルの3段 Pipeline を組む口（`build_estimator`）と、落ちない・漏れない・決定的の既定を
焼き込んだエンコーダのレジストリ（`ENCODERS`）。設計は Fable（sklearn 1.9 実測で裏取り）。

## 受け入れ基準（テスト先行で）
- `build_estimator(spec, model, *, seed)`：features(BLOCKS)→encode(ColumnTransformer/ENCODERS)→model の2〜3段。生カテゴリ列は features 段の columns で通す。早期検査（features 空・未知 kind・encode name 重複）。seed をブロック（TargetAggregate 等）へ注入。
- `ENCODERS`（kind→sklearn 工場）：**params は sklearn へ素通し（写経しない）**。焼く既定は「落ちない・漏れない・決定的」だけ——OneHot は `handle_unknown="infrequent_if_exist"`（未知で落ちない）／Ordinal は未知/欠損 -1／TargetEncoder は `cv=KFold(seed)`（非推奨 shuffle/random_state を使わない決定的 OOF）／KBins・PCA は SimpleImputer 前置（NaN で落ちない）／Tfidf は null 空文字埋め・PCA は標準化前置＋n_components 必須。性能の好み（分割数・語彙サイズ）は焼かない。
- 漏れ二重：外＝run_cv の clone-per-fold（encode も fold の train だけで学習・未知カテゴリを valid に置いた分割で categories_ に入らない）／内＝TargetEncoder の cross-fitting（est[:-1] の fit_transform≠fit.transform）。決定的（同 spec・seed で一致）。
- 列名追跡：`estimator[:-1].get_feature_names_out()` が features→encode を通り manifest まで届く。
- 置き場＝新 `src/harness/ds/pipeline.py`（features.py と別・1責務）。E-0001 は無変更（E-0002 から利用）。`uv run verify` 全成功。
