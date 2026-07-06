---
id: T-0057
kind: task
status: done
title: チューニング継ぎ目（*SearchCV を model に被せる＝run_cv で nested CV 無料・optuna は optional）
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_tune.py::test_search_picks_good_side
  - tests/test_ds_tune.py::test_search_is_deterministic_with_seed
  - tests/test_ds_tune.py::test_nested_cv_seam_with_run_cv
  - tests/test_ds_tune.py::test_build_model_without_tune_is_unchanged
  - tests/test_ds_tune.py::test_build_model_with_tune_wraps_and_wires_seed
  - tests/test_ds_tune.py::test_grid_and_halving_tuners
  - tests/test_ds_tune.py::test_unknown_tuner_and_missing_params_raise
  - tests/test_ds_tune.py::test_tuners_have_docstrings
---
# T-0057 チューニング継ぎ目

## 背景・設計
ハイパラ探索を「モデルに被せる SearchCV」で表す。SearchCV を **model 段**に置けば、run_cv が fold ごとに
clone→train で fit する既存構造がそのまま **nested CV**（外側=run_cv の fold・内側=SearchCV の cv）になる＝
リークなしのチューニングが追加コードなしで手に入る。参考リポの optuna を当リポ流儀（registry・config）へ翻案。

## 受け入れ基準（sklearn 素通し・DEC-0006）
- 新ファイル `src/harness/ds/tune.py`：
  - `TUNERS` レジストリ（Entry・registry.py 流用）：`random`→`RandomizedSearchCV`、`halving`→`HalvingRandomSearchCV`
    （`from sklearn.experimental import enable_halving_search_cv` が必要）。`grid`→`GridSearchCV` も可。
    optuna は **optional extra**（`importlib.util.find_spec("optuna")` で条件登録＝lightgbm/skops と同じ）。
  - `build_tuned(model, tune_spec, *, seed, inner_cv=3) -> SklearnLike`：`tune_spec`（config 由来 dict：`tuner`・
    `param_grid`（モデル自身のパラメタ名→候補リスト）・`n_iter` 等）から選んだ *SearchCV で model を包んで返す。
    内側 cv は seed 付き（`KFold`/`StratifiedKFold(shuffle=True, random_state=seed)` か整数）。`refit=True`（best で予測できる）。
- 配線：`pipeline.build_model`（か build_estimator）で spec に `tune:` があれば built model を `build_tuned` で包む。
  無ければ従来どおり素の model（**既存挙動は完全に不変**）。SearchCV が `classes_`/`predict_proba` を委譲し
  `cv._predict` がそのまま使えることを確認（多クラス・二値とも）。
- カタログ：`data tuners`（任意）か既存カタログに TUNERS を載せる（description 必須・DEC-0009）。最低限 registry に description。

## 触ってよいファイル
新規 `src/harness/ds/tune.py`＋`src/harness/ds/pipeline.py`（build_model の tune 配線のみ）＋`tests/test_ds_tune.py`（新規）。
`eval.py`/`cv.py`/`features.py`/`models.py`/`experiment.py` は触らない（並行作業あり）。CLI カタログ配線は別途でよい（registry の description は必須）。

## 検査（テスト先書き・構成から導く）
- `build_tuned` が包んだ SearchCV を `run_cv` に通すと fit/predict が通り、best_params_ が候補の中から選ばれる。
  構成：ある 1 つのハイパラ値だけが明確に良いデータ（例：logreg の C が小さいと悪く大きいと良い分離データ）で、
  探索が「良い側」を選ぶ（構成から良い側が導ける・実装出力の写経でない）。
- 内側 cv が seed 付きで**決定的**（同 seed で同じ best_params_）。
- tune 無しの spec は従来 build_model と同一の型（回帰なし）。
- 未知 tuner は ValueError（候補を挙げる）。

## 独立レビュー（2026-07-06・maker≠checker）
核心（nested CV でリークなし・決定性・build_model の後方互換・_predict 委譲・テストの構成由来）を**実測で確認**
（外側 fold の train だけで内側 cv が回り valid を見た fit は 0 回）。important 1：optuna の条件登録が `find_spec("optuna")` だけ
＝OptunaSearchCV が optuna>=4 で別配布物 optuna-integration に移ったため「登録されるのに使えない」罠 → 検出を
`_optuna_available()`（新旧両配置を find_spec）・import を新旧フォールバックに直し、extras_hint も設定。minor（optuna extra 未追加・
data tuners コマンド未配線・spec に refit/cv 明示で TypeError）は [[ISS-0012]] に集約（CLI 配線タスクで拾う）。

## 結果
実装・独立レビュー（optuna 検出の是正を反映）・verify 緑で done。参考リポ optuna 取り込み＝ideal-build-plan Wave 3・§参考。
