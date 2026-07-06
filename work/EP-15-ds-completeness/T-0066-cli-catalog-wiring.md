---
id: T-0066
kind: task
status: done
title: CLI カタログ配線（data selectors / data tuners）＝レビュー指摘の死にポインタ解消
created: 2026-07-06
depends_on: [T-0057, T-0064]
verified_by:
  - tests/test_catalog.py::test_catalog_commands_run
  - tests/test_catalog.py::test_selectors_have_docstrings
  - tests/test_ds_tune.py::test_tuners_have_docstrings
---
# T-0066 CLI カタログ配線

## 背景
T-0057（TUNERS）・T-0064（SELECTORS）で `Registry(catalog="data tuners"/"data selectors")` を設定したが CLI コマンドは
未配線＝未知 kind のエラー文が存在しないコマンドを案内する「死にポインタ」（両レビューの minor 指摘）。
`data models`/`data encoders` と同型のカタログコマンドを足して DEC-0009 の導線を閉じる。

## 受け入れ基準
- `ds/cli.py` に `data selectors`（SELECTORS）・`data tuners`（TUNERS）を追加（既存カタログコマンドと同じ `render_catalog` 呼び）。
  それぞれ使い方の 1 行（select は to_numpy と model の間・tune は model 節の tune: ＝nested CV）を添える。
- `test_catalog_commands_run` が両コマンドの出力に selectkbest/variance_threshold・random/halving が載ることを検査。
- 既存コマンド・レジストリは不変（追加のみ）。

## 結果
実装（コマンド 2 つ＋スモーク拡張）・verify 緑で done。ISS-0012 の CLI 配線部を消化（optuna extra 導入は owner 判断で ISS 継続）。
軽微・確立パターンの複製のため独立レビューは test_catalog の機械検査（description 必須＋出力検査）で代替。
