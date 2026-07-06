---
id: T-0087
kind: task
status: done
title: data monitor（配信ログ×学習基準の psi/drift 監視表・prediction monitoring の翻案）
created: 2026-07-06
closed: 2026-07-06
verified_by: [tests/test_ds_monitor.py]
depends_on: [T-0048]
---
# T-0087 data monitor

## 背景（DEC-0013・prediction monitoring の翻案）
配信の分布ドリフトを監視する入口。計算は ds 側（部品 eda.psi/drift_auc・store.load が ds 圏）。serve は「ログを書く側」、
ds は「読む側」で、結合は JSONL 行スキーマ（docs/serve.md の契約・T-0085 が正本）だけ。ds→serve の import は作らない。

## 受け入れ基準（既存部品の再利用・門番にしない）
- **新モジュール `src/harness/ds/monitor.py`**（純関数・テスト可能）：配信ログ（JSONL glob）と学習基準テーブルを受け、共通列ごとに
  `eda.psi(baseline[c], served[c])`→行 `{column, psi, band}`（band は psi の目安 0.1/0.25 で 安定/要注意/大変化）。`--auc` 時は数値
  共通列で `eda.drift_auc`。予測列は分位・平均の要約（基準に対応物が無いので比較でなく要約）。**psi はビン境界を基準の分位からのみ作る＝
  リーク無し**。壊れ行・スキーマ不一致は警告して読み飛ばし（監視が盲目になるより縮退）。
- **`ds/cli.py` に `data monitor`**：`--baseline <table_id> --log <glob> [--columns] [--auc] [--seed] [--since YYYY-MM-DD]`。log 既定
  `artifacts/serve/predictions/**/*.jsonl`。ログの `features` struct を unnest→配信入力 DataFrame。出力は `data compare` と同型の YAML
  （baseline/log/n_baseline/n_served/psi[]/drift/prediction_summary）。**exit 0（門番にしない）・読込不能時のみ非 0**。eda スキルか
  serve スキルの導線に 1 行（DEC-0009）。

## 触ってよいファイル
`src/harness/ds/monitor.py`（新規）・`src/harness/ds/cli.py`（data monitor のみ）＋`tests/test_ds_monitor.py`（新規）。
`eda.py` の psi/drift_auc は**呼ぶだけ・変更しない**。serve パッケージは import しない。

## 検査（テスト先書き・契約どおりの JSONL を直接書く＝serve 起動しない）
- 契約どおりの JSONL を手で書き（T-0085 の行スキーマ）、同一分布サンプルで psi≈0・平行移動で psi>0.25・drift_auc が 0.5/1.0 近傍。
- 壊れ行の読み飛ばし警告・空ログの縮退・`--since` フィルタ・CLI スモーク（YAML が出る・exit 0）。

## 独立レビュー（maker≠checker・差分のみ・実測）
別セッションの独立レビュアーが commit `7e05cc0` の差分だけを実測（4 種の変異＝psi 閾値・since フィルタ・
型不一致スキップ・features キー不一致スキップは正しく検知／契約照合＝JSONL キーが docs/serve.md・
runtime.PREDICTION_LOG_FIELDS と一致・serve 非 import／CLI 縮退を CliRunner で確認）。
指摘 1 件（`monitor.py` の `served.n_rows == 0` ガードの変異が既存テストで生き残る＝列 0 個の空フレーム
だけを渡していた穴。実運用経路では未発現だがカバレッジの穴）→ 列一致の 0 行 ServedLog も試す形にテストを
強化し変異を殺した（commit `ef34d33`・RED→復元 17 件緑を実測）。金メッキ無し・リーク無しを確認。
