---
id: T-0049
kind: task
status: done
title: モデル形式の継ぎ目を skops で完成（FORMATS レジストリ＋安全読込の信頼リスト）
created: 2026-07-05
verified_by:
  - tests/test_ds_models.py::test_format_roundtrip
  - tests/test_ds_models.py::test_unknown_format_is_rejected_with_hint
  - tests/test_ds_models.py::test_skops_roundtrip_stateful_pipeline
  - tests/test_ds_models.py::test_skops_save_fails_loud_on_untrusted_type
  - tests/test_ds_models.py::test_skops_load_rejects_untrusted_file
  - tests/test_ds_models.py::test_skops_load_corrupt_file_raises_valueerror
---
# T-0049 モデル形式の継ぎ目を skops で完成

## 受け入れ基準
- `FORMATS`（`ModelFormat` dataclass：dump/load/file_name/description）を registry 化。`pickle` は常に登録（既定・
  後方互換）、`skops` は `find_spec` 条件登録（optional extra・import ゼロで判定）。`save_model(format=)` で選ぶ。
- **skops 安全読込**：`TRUSTED_HARNESS_TYPES` に無い型は `_skops_load` が `load` 到達前に `ValueError`（外部/改竄
  ファイルへの ACE 防御）。信頼リストは当リポの状態持ちパイプライン（GroupAggregate/TargetAggregate の polars/KFold、
  cluster/anomaly の numpy、lightgbm 型など）を網羅（実測で確定）。
- **保存時 fail-loud**：`_skops_dump` は保存直後に信頼リスト外の型が無いか確かめ、あれば `ValueError`。
  「保存できるが読めないモデル」を作らない（`atomic_write` が tmp を消すので不完全な保存も残らない）。

## 結果
実装（FORMATS・skops dump/load・信頼リスト・保存時 fail-loud）・テスト先書き（往復＝状態持ちパイプライン、
save 時 fail-loud、load 拒否＝外部ファイル相当の3本＋形式往復/未知形式）・独立レビュー（信頼リスト不足の
CONFIRMED 指摘を反映）・verify 緑で完了。`docs/ideal-build-plan-2026-07-05.md` Wave 2・DEC-0006/DEC-0011
（structure-review §低⑫の「format 継ぎ目」を消化。ISS には紐づかない設計上の継ぎ目）。

## 独立レビュー（2026-07-06・maker≠checker）
ACE 防御・信頼リスト網羅性・save fail-loud を**実測で確認**（悪意 `__setstate__` ファイルを load→未実行で拒否／
全ブロック×全エンコーダ×全モデル種 12 構成で untrusted 取りこぼしゼロ／未信頼型 save で残存ファイルゼロ）。
important 1 件（save 残存チェックが誤パス `artifacts/` を見て空振り＝金メッキ）を修正：`proj.root` 全体を
`*.skops`/`*.skops.tmp` で走査。minor 2 件（壊れ .skops の例外型・前方互換の StratifiedKFold コメント）も反映。
