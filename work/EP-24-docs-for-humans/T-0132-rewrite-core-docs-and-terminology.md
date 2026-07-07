---
id: T-0132
kind: task
status: todo
title: 中核ルール文書（AGENTS/method/charter/DoD/template-copy/README/learnings）刷新＋造語denylist検査＋review観点
created: 2026-07-07
depends_on: [T-0131]
verified_by: []
---
# T-0132 中核ルール文書の刷新＋用語執行の仕上げ

## 狙い
残る中核文書を人間可読に刷新し、造語の執行（denylist 検査）と review 観点を足して、EP-24 を閉じる。

## 書き換え（DEC-0019 に従う・T-0131 と同じ原則）
- **`AGENTS.md`**：これは**規範（エージェントが従う決まり）＝規範性を 1 つも弱めない**。意味・ルールは保持し、
  可読性だけ直す：冒頭に「この文書は何で誰が従うか」の平易な導入、監査指摘の長文（15 行目等）を箇条書きに、
  造語を用語集リンクに。ルールの追加・削除・緩和はしない（レビューで diff を厳格に確認する）。
- **`method.md`**：歩く骨組み(walking skeleton)・全体→詳細・昇格(規則)・ラチェットを標準語＋用語集リンクで。
  HTML コメントに隠れた導入を可視化。
- **`charter.md`・`DoD.md`・`template-copy.md`**：平易な導入を保ちつつ用語を用語集に合わせる。template-copy は
  How-to（新規案件の始め方）として手順を明快に。
- **`README.md`（ルート）**：人間の地図として整える。冒頭の平易化・専門語の初出説明・`docs/README.md`（詳しい
  索引）への明確な誘導。コマンド early は残すが、その前に「まず docs/README.md を読む」導線。
- **`docs/learnings.md`**：フォーマット説明の導入を明快に（造語→用語集）。
- **スキル導線**：残るスキルの説明文が人間にも意味が通るよう用語を用語集に合わせる（手順は保つ）。

## 仕組みの仕上げ
- **`doc_standards` に造語 denylist 検査を追加**：`docs/**` 本文で、**用語集で標準語に置換すべき最悪造語**が
  用語集リンク無しに使われていたら error（または warning＋修正提案）。最低限：`金メッキ`（→「入力から
  導けないハードコード期待値」）。加えて**用語の不統一検査**：同一概念の別名が混在（例 `門番` と `関門` を
  gate の意味で混用）を検出できる形にする。判定は「その語が用語集に定義され、使用箇所が用語集にリンクするか
  初出定義を伴う」＝Google style の初出定義規則の機械化。理由必須 allowlist。**誤検出を避けるため対象語は
  用語集で明示宣言した最悪造語に限定**（jargon 全部は機械化しない＝正直な線引き。残りは review 観点）。
- **`.claude/skills/review/SKILL.md` にドキュメント観点を追加**：機械が判定しない質的規律のチェックリスト
  （初見で理解できるか／全体像→詳細か／過不足ないか／標準用語か／Diátaxis の正しい種別か）。

## テストの要点
- denylist 検査：一時 doc に `金メッキ` を用語集リンク無しで書く→error、用語集リンク付き or 標準語→緑。
- 不統一検査：`門番` と `関門` を gate の意味で混在→検出（構成から期待値を導出）。
- 現リポ回帰：`doc_standards.run_checks(REPO_ROOT)` が空（刷新後の全文書が denylist/lede/孤立/凡例/用語集を
  満たす＝緑）。既存テスト全緑。markers 必須。
- **AGENTS.md の規範不変の確認**：刷新前後で「原則・してはいけないこと・テストの決まり」の各条が保持されて
  いることをレビューで確認（テストでは全文書 verify 緑＝壊れていないことを担保）。

## 触ってよい範囲
`AGENTS.md`・`README.md`・`docs/method.md`・`docs/charter.md`・`docs/DoD.md`・`docs/template-copy.md`・
`docs/learnings.md`・`docs/README.md`・`docs/glossary.md`・`.claude/skills/**/SKILL.md`（説明文の用語のみ）・
`.claude/skills/review/SKILL.md`（観点追加）・`src/harness/doc_standards.py`・`tests/test_doc_standards.py`・
この item.md。CLAUDE.md（AGENTS 取り込みの 2 行）は変えない。
