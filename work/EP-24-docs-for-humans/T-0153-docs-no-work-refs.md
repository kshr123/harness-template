---
id: T-0153
kind: task
status: done
title: 恒久ドキュメントが work/ の作業単位を参照しないよう直す（設計の正本は DEC へ・複製で消える依存を断つ）
created: 2026-07-07
depends_on: []
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0153 恒久ドキュメントの work/ 参照を断つ

## 背景（オーナー指摘）
`docs/ops.md` が設計の理由を `work/EP-21-ops-profile/item.md` の「やらないこと」に参照していた。`work/` は
**作業の進行を追う一時的な単位（エピック・タスク）**で、テンプレートを新しい案件へ複製すると中身は消える／
置き換わる。恒久ドキュメント（Reference・正本）が `work/` に依存すると、複製先でリンク切れになり、設計の
正本が一時物に乗る。恒久ドキュメントは DEC（決定の記録＝恒久）か本文自体に根拠を置くべき。

## 直したもの
- **`docs/ops.md`**：「やらないこと」の理由・順序の根拠を `work/EP-21…` 参照から、本文の説明＋
  `DEC-0014`（対象は ML ライフサイクル全体・重い実行時基盤は利用者環境の関心で後回し）へ。
- **`docs/agent.md`**：proactive の loops 写像表の参照を `work/EP-23-loops/item.md` から `DEC-0018`
  （loops 語彙の ds/serve/ops への写像）へ。
- **`README.md`**：構成例の `work/EP-01-foundation/…`・`work/EP-06-…` を、特定エピックに依存しない
  プレースホルダ（`work/<エピック>/…`）へ。テンプレートが特定の作業単位を前提にしない。

## 対象外（正当な work/ 参照）
`docs/template-copy.md` の `work/EP-06-…` は**複製手順の一部**（前案件のエピックフォルダを消す指示）＝
work/ への依存でなく work/ の扱いの説明なので、そのまま。

## 受け入れ基準
- `uv run verify` 全成功（doclint がリンク整合を確認）。
- 恒久ドキュメント（README・AGENTS・docs/*.md、template-copy を除く）が `work/EP…`・`work/T-…`・`work/E-…`
  を設計の根拠として参照しない。

## 触ってよい範囲
`docs/ops.md`・`docs/agent.md`・`README.md`・この item.md。
