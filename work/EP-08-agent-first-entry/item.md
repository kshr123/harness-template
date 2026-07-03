---
id: EP-08
kind: epic
status: in-progress
plan: detailed
title: 部品を使える入口（エージェントファースト化）
requirements: [REQ-004]
created: 2026-07-03
---
# EP-08 部品を使える入口（エージェントファースト化）

## 目的
作った部品（features/pipeline/models/experiment・BLOCKS/ENCODERS）が、将来のエージェントに**再コーディング
させず「使われる」**ようにする。目的は「コードを作ること」でなく「エージェントファーストなプロジェクト開発」。
設計は Fable。診断＝部品は良い形だが「エージェントが発見して使う入口」（一覧コマンド・スキル・雛形）が欠けていた。

## 進め方（Fable の T-A→T-B→T-C）
- T-0021 カタログ出口：`uv run data blocks` / `data encoders`（レジストリから生成）＋工場に docstring＋説明文必須テスト。
- T-0022 E-0001 の雛形化：train.py を `build_estimator` ベースに（雛形＝コピー元の正本・verify の e2e が毎回実行＝腐らない）。
- T-0023 スキルと規約：experiment / features スキル新設＋DoD/AGENTS/method に「部品は入口まで作って完了」＋DEC-0009。
