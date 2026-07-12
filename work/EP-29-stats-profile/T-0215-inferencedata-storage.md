---
id: T-0215
kind: task
status: done
title: InferenceData を manifest つきで保存・読込する（正本は netCDF・format 文字列で分岐）
created: 2026-07-11
depends_on: [T-0213]
verified_by:
  - tests/test_stats_store.py::test_save_load_roundtrip_preserves_posterior
  - tests/test_stats_store.py::test_tampered_file_is_rejected_on_load
  - tests/test_stats_store.py::test_version_is_not_reused
  - tests/test_stats_store.py::test_unsupported_format_is_rejected
---
# T-0215 保存の正本を InferenceData にする

## 何が問題か
stats の正本は `InferenceData`（事後分布そのもの）で、点推定の指標に潰すと保存すべきものが壊れる。
`harness.storage` の作法（manifest＝版・作成元データ・形式のメタデータ 1 枚）に載せないと、
どのデータ・どの宣言から得た事後かを後から照合できない。

## やること
- `InferenceData` を netCDF（T-0211 で確定した保存ライブラリ）で保存し、manifest の `format` 文字列で
  load を分岐する（ds の `models.py` と同じ拡張点の形。核は形式ライブラリを直接固定しない）。
- manifest に由来を残す：入力データの fingerprint・モデル spec・サンプラー（フォールバックの記録込み）・
  draws／tune／chains・seed。
- 保存の置き場は `harness.storage` の既存の作法に従う（二重化しない。stats 専用の保存機構を発明しない）。

## やらないこと
- 可搬形式（zarr 等）への今の対応（要る時に `format` の分岐へ枝を足す。拡張点だけ空けておく）。
- 事後の要約統計だけを保存する軽量形式（正本を潰す圧縮はしない）。

## 受け入れ基準
- 保存 → 読込の一往復で `posterior` の値が一致する（往復の同一性は構成から導ける）。
- 入力データを 1 行変えると manifest の fingerprint が変わる（fingerprint の定義から導ける）。
- manifest に seed・サンプラー名・draws が残り、別の立場が manifest だけから再実行の引数を再構成できる。
- `uv run verify` 全成功。
