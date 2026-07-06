---
id: ISS-0008
kind: risk
state: open
found_in: ds-review-2026-07-05
created: 2026-07-05
title: レジストリの形がばらつき、DATA_SOURCES にだけ一覧コマンド（入口）が無い
---
# ISS-0008 レジストリ形のばらつきと DATA_SOURCES の入口欠落

## 事象
7 つのレジストリが精神は同じで形が違う：`MODELS`→`ModelEntry(factory, task)`、`METRICS`→リッチな `Metric`、
`BLOCKS`→クラス、`ENCODERS`/`CLUSTERERS`/`DIMRED`/`ANOMALY`/`TS_MODELS`/`DATA_SOURCES`→裸の callable。
説明文は docstring 先頭行を `test_catalog` が必須検査し、CLI はレジストリごとに描画ループを手書き。
さらに `DATA_SOURCES`（`data.py`）にだけ `uv run data <x>` の一覧コマンドが無く、`load_dataset` の docstring が
指す `data list` はテーブル一覧であって源種の一覧ではない。

## 根拠・影響
`DATA_SOURCES` は実データ配線で最初に触るレジストリなのに、DEC-0009（「部品は入口まで作って完了」）の入口が無い＝
自己違反。`docs/structure-review-2026-07.md` §低⑩が「カタログ汎用化・レジストリ機構の中核昇格」を Rule of Three で
保留と決めており、本レビューは 2 回目の実例。

## 対処の方針（決めてから）
`Entry(factory, description, task=None, tags=())` 系へ形を寄せ（description は docstring 由来で既存テスト維持）、
CLI に汎用 `render_catalog(registry)` を 1 本。あわせて `data sources` を追加し `test_catalog` に載せる。
昇格は 2 つ目のドメインが出た時（機会を見て小さく）。
