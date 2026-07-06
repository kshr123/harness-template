---
id: EP-14
kind: epic
status: done
title: 保存とレジストリの継ぎ目刷新（storage 正本・registry 統一・skops・checks 実評価）
plan: detailed
requirements: [REQ-002]
created: 2026-07-05
---
# EP-14 保存とレジストリの継ぎ目刷新

## 目的
`docs/ideal-build-plan-2026-07-05.md` の Wave 2。DEC-0010 に基づき、保存の「4作法」とレジストリの形を正本 1 か所へ寄せ、
モデル形式の継ぎ目を skops で完成し、schema の `checks` を実評価にする。ISS-0006/0008/0010＋structure-review §低⑫を消化。

## 進め方（Round 1＝並列・Round 2＝storage 後）
- **T-0047 storage.py 抽出**：URI 解決／原子書き込み／`file_digest` 指紋／manifest 読み書きの正本を core `harness/storage.py` に。
  store/models/schema は薄い方針層に。非 file: URI を fail-loud で統一（schema の黙示フォールバック廃止）。
- **T-0048 registry.py 統一＋汎用カタログ**：9 レジストリを `Entry`/`Registry` に。CLI に `render_catalog`＋`data sources`。
  description は docstring 由来（test_catalog の精神維持）。
- **T-0049 skops format 継ぎ目**（storage 後）：`FORMATS` レジストリ＋`save_model(format=)`＋skops（optional extra・信頼型リスト）。既定は pickle。
- **T-0050 schema checks 実評価**（storage 後）：`Column/TableSchema.checks` を `pl.sql_expr` で評価（pandera 不採用・DEC-0011）。

## やらないこと
pandera 導入（導出スケッチは DEC-0011 に添付）。format 既定の skops への反転（次のテンプレ複製時）。
