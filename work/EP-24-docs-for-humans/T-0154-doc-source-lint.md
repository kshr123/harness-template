---
id: T-0154
kind: task
status: done
title: doc_source_lint＝恒久ドキュメントの work/ 参照を verify で止める（複製時の壊れを機械で防ぐ）
created: 2026-07-07
depends_on: [T-0153]
verified_by: [tests/test_doc_source_lint.py::test_durable_doc_referencing_work_item_is_error, tests/test_doc_source_lint.py::test_real_repo_durable_docs_have_no_work_refs]
---
# T-0154 恒久ドキュメントの work/ 参照を機械で止める

## 背景
T-0153 で手作業で直したが、再発を止める仕組みが無かった。オーナー要望：機械化で防ぎ（重くない範囲）、
検知したら直せるようにする。これは体裁でなく**複製時にリンクが壊れる correctness**（前回避けた「体裁の
機械化」とは別物）。既存の検査を見直した結論：doclint（参照が実在するか＝dead link）はあるが、「恒久
ドキュメントが work/ に依存しない（複製で消えるため）」は誰も見ていない＝ここが穴。

## やったこと（理想の最小構成）
- **`src/harness/doc_source_lint.py`（新 core 検査）**：恒久の読み手向け文書（`README.md`・`AGENTS.md`・
  `docs/*.md` 直下、`template-copy.md` を除く）に**具体的な作業単位への参照**（`work/EP-…`/`T-…`/`E-…`/`INV-…`）が
  あれば error。プレースホルダ（`work/<…>`）・契約のパス型（`artifacts/…`・`results/…`）・履歴の記録
  （`docs/decisions/`・`docs/archive/`）は対象外＝**高精度・低誤検知**。理由必須 allowlist（`template-copy.md`）。
  stdlib のみ・無ネットワーク・軽量。`PM_CHECKS`（verify）へ配線。
- **検知したら直す仕組み**：エラーメッセージが file:line:参照 と直し方（DEC を指すか本文に根拠を書く／複製
  手順なら template-copy.md へ）を名指しする。verify が done 前に止めるので、直す→緑、で閉ループ。
  ※参照の正しい差し替え先（どの DEC か）は判断が要るので自動書き換えはしない（誤修正を避ける）。
- **AGENTS.md に規約 1 行**（検査点つき）：「恒久ドキュメントは work/ を設計の根拠に参照しない」。

## 対象を work/ に絞った理由（一般化しすぎない）
`artifacts/`・`results/`・`data/` は恒久ドキュメントに**契約のパス型**として載るのが正しく、禁じると誤検知
になる。作業単位 ID の provenance（DEC・learnings が「T-0095 で実装」と書く）も履歴として正当。機械で安全に
止められるのは「恒久ドキュメント → 具体的な `work/…` パス」だけ＝ここに絞る（正直な線引き。残りはレビュー）。

## 受け入れ基準
- `uv run verify` 全成功（doc_source_lint 込み・現リポの恒久ドキュメントは work/ 参照ゼロ）。
- 恒久ドキュメントに `work/EP-…` を書くと verify が落ち、メッセージが直し方を示すことを回帰テストで固定
  （maker≠checker：本タスクは Opus が実装＋変異検査で検出の有効性を確認済み）。

## 触ってよい範囲
`src/harness/doc_source_lint.py`（新規）・`src/harness/checks.py`（PM_CHECKS へ 1 行）・
`tests/test_doc_source_lint.py`・`AGENTS.md`（規約 1 行）・この item.md。
