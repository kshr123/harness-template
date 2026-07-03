---
id: T-0034
kind: task
status: done
title: 時間順分割（ML方式の時系列）make_time_folds・fold_indices expanding・order_by
depends_on: [T-0031]
created: 2026-07-03
verified_by:
  - tests/test_ds_cv_timeorder.py::test_time_folds_expanding_is_past_to_future
  - tests/test_ds_cv_timeorder.py::test_run_experiment_order_by_excludes_oldest_fold
  - tests/test_ds_cv_timeorder.py::test_order_by_and_stratify_are_exclusive
---
# T-0034 時間順分割（T-D・ML方式の時系列）

## 受け入れ基準
- `cv.make_time_folds`（order_by で並べ時間ブロックに等分・shuffle なし・seed 不要）＋`fold_indices(how="expanding")`
  （fold k を valid・fold<k を train＝過去→未来・fold 0 は学習専用で OOF に入らない）。run_cv は無変更で受ける。
- `run_experiment(order_by=)` で切替（stratify_by と同時指定はエラー）。experiment スキルに1行。
- 期待値は構成（時刻=行番号）から導出：全 fold で max(train 時刻)<min(valid 時刻)・最古ブロックは未カバー。

## 結果
実装・verify 緑。時系列は「新しいモデルでなく新しい分割」＝回帰モデルを時間順で正直に評価できる。ラグ特徴は最初の
時系列実験で features に追加（Rule of Three）。古典時系列（ARIMA 等）は T-0035（別経路）。
