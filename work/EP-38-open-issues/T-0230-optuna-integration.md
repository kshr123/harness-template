---
id: T-0230
kind: task
status: done
title: optuna チューナーを all-extras に入れて CI で実行する（extra 追加＋OptunaSearchCV のテスト）
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by:
  - tests/test_ds_tune.py::test_optuna_search_picks_good_side
---
# T-0230 optuna チューナーの完全統合

## 事象
チューニングの継ぎ目（`tune.py`）は OptunaSearchCV を条件登録する形で完成していた（`_optuna`・
`_optuna_search_cls`・`_optuna_available`・extras_hint）が、verify 環境（`uv sync --all-extras`）に
optuna が入っていないため、登録コードがあるのに CI で一度も実行されない状態だった。「開発・verify 環境は
all-extras＝optional のテストを skip しない」（AGENTS.md）の趣旨に対し optuna だけ抜けていた。

## 直し方（着手前に installability を実測＝L-020）
- Python 3.14.6 で `optuna>=4` + `optuna-integration>=4` が解決・導入できることを dry-run と実 sync で確認
  （optuna==4.9.0・optuna-integration==4.9.0）。
- pyproject に `optuna = ["optuna>=4", "optuna-integration>=4"]` extra を追加（`--all-extras` に自動で入る）。
  OptunaSearchCV は optuna>=4 で別配布物 optuna-integration へ移管済みなので 2 つ明示。
- mypy overrides に `optuna.*`・`optuna_integration.*` を追加（ignore_missing_imports）。
- `tests/test_ds_tune.py::test_optuna_search_picks_good_side`：分離データで TPE が良い側（C=100）を選ぶ。
  期待値は `_separable` の構成から導ける（実装出力の写経でない）。importorskip で未導入環境では skip。

`data tuners` の CLI 配線は T-0066 で完了済み（ISS-0012 の残タスクは 1・2 だけ）。
