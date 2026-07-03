---
id: T-0022
kind: task
status: done
title: E-0001 を build_estimator ベースの雛形にする（コピー元の正本）
requirements: [REQ-004]
depends_on: [T-0020, T-0021]
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_smoke
  - tests/test_e2e_experiment.py::test_e0001_two_variants_share_folds
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0022 E-0001 の雛形化

## 目的
E-0001 の train.py が手書きの if 分岐で estimator を組んでいた（コピーすると「部品を使わない実験」を再生産）。
`build_estimator`（config 駆動）ベースにして、**コピー元の正本＝雛形**にする。雛形は verify の e2e が毎回実行する
ので腐らない（`.harness/templates/` に別置きすると誰も実行せず腐る、を避ける）。

## 受け入れ基準
- code/train.py：ローカル build_estimator を削除し `from harness.ds.pipeline import build_estimator` に差し替え。CV・保存・閾値は再実装しない（部品が正本）。
- config.yaml：variants を build_estimator の spec 形式（features / encode 節）に。`--variant` の選択肢は config の variants キーから導出（コピー先で config だけ書き換えれば動く）。
- e2e（test_e0001_smoke・two_variants_share_folds）が緑のまま・**指標は不変**（差し替えの意味が同一である証拠）。results は再生成しない。
- train.py 冒頭に「以後の実験のコピー元（雛形）・experiment スキル参照」と明記。`uv run verify` 全成功。
