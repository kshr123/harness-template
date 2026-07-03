---
id: E-0001
kind: experiment
status: in-progress
plan: detailed
title: 交互作用特徴量 x1*x2 で予測が改善するか
requirements: [REQ-004]
depends_on: [T-0013, T-0014]
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_smoke
  - tests/test_e2e_experiment.py::test_e0001_two_variants_share_folds
created: 2026-07-03
owner: sakurada
---
# E-0001 交互作用特徴量 x1*x2 で予測が改善するか

歩く骨組みとして baseline を `--test` で端から端まで通す（データ生成→特徴量→交差検証→合否→results）。
詳細は SPEC.md、実行体は code/train.py、設定は config.yaml。
まだ in-progress（骨組み）：以降で store 保存・モデル保存・閾値選択・interaction 変種・本規模実行を足して done にする。
