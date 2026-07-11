---
id: T-0186
kind: task
status: done
title: run_experiment に group_by を通し、GroupKFold を実験の正規経路から使えるようにする
created: 2026-07-10
closed: 2026-07-11
depends_on: []
verified_by:
  - tests/test_ds_experiment.py::test_run_experiment_group_by_prevents_group_leak
  - tests/test_ds_experiment.py::test_run_experiment_without_group_by_leaks_groups
  - tests/test_ds_experiment.py::test_run_experiment_group_by_rejects_with_order_by
---
# T-0186 GroupKFold が実験から到達できない

## 何が問題か
`src/harness/ds/cv.py` の `make_folds` は `group_by` を受け取り、`GroupKFold` / `StratifiedGroupKFold` を
選べる。ところが `run_experiment` は `group_by` を**そもそも受け取らない**。つまり分割器としては実装
されているのに、実験の正規経路（config → `run_experiment`）からは一生使われない。

同じ実体が複数行に現れるデータ（1 人が複数行・1 店舗が複数日）で、group を指定せずに交差検証すると
リークする。リークした指標は「良い結果」に見えるので、黙って間違った答えを出す側の欠陥である。

（この欠落は T-0182 の主張「分割器だけが唯一、拡張口の無い軸」を検証する過程で見つかった。
拡張口の有無より先に、既にある口が配線されていないことの方が実害が大きい。）

## 何をするか
- `run_experiment` の config に `group_by`（列名）を通し、`make_folds` へ渡す。
- 実験の記録（`results/`）に、どの列で group 分割したかを残す（後から「リークしていない」と言えるように）。

## 受け入れ基準
- 同じグループの行が train と valid に跨がらないことを、テストデータの構成から導いて確かめる
  （実装の出力をコピーした固定値を書かない）。
- `group_by` を指定しない既存の config の挙動は変わらない（既存テスト無変更で全成功）。
- `uv run verify` 全成功。

## やらないこと
- 分割器のレジストリ化（EP-30 の T-0182）。ここでは既にある分割器へ config を繋ぐだけ。
