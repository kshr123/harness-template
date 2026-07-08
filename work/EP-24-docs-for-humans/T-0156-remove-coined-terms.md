---
id: T-0156
kind: task
status: done
title: プロジェクト内造語を全廃（docs＋コード）＝標準語・平易語・英語の実フィールド名に統一
created: 2026-07-08
depends_on: [T-0155]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links, tests/test_structure.py::test_templates_have_owner_checks]
---
# T-0156 プロジェクト内造語を全廃する

## 背景（オーナー指摘）
README の「指紋」が意味不明、という指摘から拡大。オーナー方針：**プロジェクト内造語は 1 つも許さない**。
英語の技術用語なら無理に和訳せず、その英語（コードの実フィールド名）に揃える。これは機械化するルールではなく
書き方の規律（造語 denylist の機械化は過去に却下済み＝[[docs-standards-dec0019]]）。

## やったこと（docs＋コード。work/ 履歴・docs/archive/ は当時の記録として残置）
置き換え（メタファ／独自語 → 標準語・平易語・英語実フィールド名）:
- 指紋 → fingerprint（内容ハッシュ）。コードの `fingerprint` フィールドと表記を一致。docs 全所を修正。
- 金メッキ → ハードコード期待値（実装の出力を丸写しした固定値）。AGENTS の定義文からも造語ラベルを撤去。
- 前半円／後半円 → 前半（検知→起票）／後半（修正→検証）。「半円」→「半分」。
- 差し替え口・（拡張の）継ぎ目 → 拡張ポイント。
- 帯（band の和訳ジャルゴン）→ 段階（安定/要注意/大変化 の 3 段階）。code の `band` フィールド名は据え置き。
- 下見（shadow のメタファ）→ 削除し標準語 shadow / canary に一本化。
- 腐り／腐り止め → 陳腐化／陳腐化防止。
- 来歴 → docs は由来（provenance）に統一。コードのコメントは辞書語のため据え置き。

残置の判断（造語でない一般語）: 正本・案件・冪等・正準・昇格・由来・番号帯。辞書にある語で初出定義済み。

## 受け入れ基準
- `uv run verify` 全成功（doclint がリンク切れ・test 群がコメント/docstring 改変の非破壊を守る）。
- docs（README・AGENTS・docs/*.md、archive 除く）とコード（src・tests）に上記造語が 0 件
  （`grep` で確認：金メッキ/前半円/後半円/差し替え口/継ぎ目/下見/腐り = 0）。
- 「造語 0」の判定は grep（人手）で行う＝造語検出の機械化は過去にオーナーが却下済みのため入れない。

## 触ってよい範囲
README.md・AGENTS.md・docs/*.md（archive 除く）・src/harness/**・tests/**・この item.md。work/ 履歴は変えない。
