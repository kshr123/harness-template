---
id: EP-24
kind: epic
status: todo
plan: detailed
requirements: [REQ-001]
depends_on: [EP-19]
created: 2026-07-07
---
# EP-24 ドキュメントを人間可読にする（Diátaxis＋標準用語＋docs_standards 検査）

## 目的
現行ドキュメントは「エージェントには読めるが人には分かりにくい」。原因は 4 つ：(1) 全体像→詳細に
なっていない（いきなり機構の説明に入る）、(2) どこに何の文書があるか分からない（人間向けの索引が無く
`docs/ops.md`・`docs/template-copy.md` は孤立）、(3) 粒度・分割・まとまりが不適切、(4) 用語が造語
（「金メッキ」「関門/門番」「導線」「昇格」の二義など）でエンジニア・データサイエンティストの一般用語に
なっていない。**人が初見で・過不足なく理解できる**ドキュメントにし、かつ**この規律を常に守らせる仕組み**を作る。

## 調査したベストプラクティス（正本にする）
- **構造＝Diátaxis**（https://diataxis.fr）：文書を 4 種に分ける — Tutorial（手を動かして学ぶ）／How-to
  （目的達成の手順）／Reference（事実・契約）／Explanation（なぜ）。全体像→詳細・適切な粒度の標準治療。
- **用語＝Google developer documentation style guide**（https://developers.google.com/style/jargon）：
  jargon は避ける。必要なら**初出で定義するか定義へリンク**。平易な語・短い文。
- **執行＝Vale の docs-as-code パターン**（https://vale.sh）：用語リスト・禁止語を CI で検査。Vale は外部
  バイナリで verify の無ネットワーク方針に合わないため、**同じ考えを stdlib の軽い検査 `doc_standards` に翻案**
  （coverage_lint と同型）。機械化できる構造（孤立・冒頭の平易な導入・凡例・用語集の整合）だけを検査し、
  「初見で理解できる」「過不足ない」の質的部分は style ガイド（正本）＋review 観点で担保する（正直な線引き）。

## 成果物（このエピックで作る）
1. `docs/README.md`＝**人間向けの入口**：平易な What/Why、読む順、ID・略語の凡例、Diátaxis 分類の文書地図。
2. `docs/glossary.md`＝**用語集**：造語→平易な定義＋標準用語（英/カナ）。二義（昇格・gate）を解消。
3. `docs/decisions/DEC-0019-*`＝**ドキュメント標準の正本**（Diátaxis・標準用語・初出定義・簡潔・発見可能）。
4. `src/harness/doc_standards.py`＝**仕組み（新 verify 検査）**：孤立文書ゼロ・各正本文書は可視の平易な導入で
   始まる・凡例の網羅・用語集の整合・最悪造語の denylist。理由必須の allowlist（他 lint と同型）。
5. **全ドキュメントの書き換え**：README／AGENTS.md／`docs/*.md`／スキルの人間可読性。標準用語＋用語集リンク＋
   長文の分割＋HTML コメントに隠れた導入の可視化。日付レビュー note は `docs/archive/` へ退避。
6. **review スキルにドキュメント観点**を追加（質的部分＝初見理解・過不足の人手チェック）。

## 進め方（歩く骨組み＝全体→詳細）
検査を「即満たせるもの」から順に入れる（ブロッキング検査を先に全部入れると全文書が一斉に落ちるため）。
- **T-0130 骨組み＋発見可能性**：`docs/README.md` 索引・`docs/glossary.md`・DEC-0019・日付 note を archive へ・
  `doc_standards`（孤立/凡例/用語集整合の即満たせる検査）を PM_CHECKS へ配線。verify 緑。
- **T-0131 Reference/プロファイル文書の刷新**：agent.md・serve.md・ops.md ＋ serve/agent スキル導線を平易な
  導入＋標準用語＋文分割で刷新。刷新後に `doc_standards` へ**導入（lede）検査**を足す（緑のまま）。
- **T-0132 中核ルール文書＋用語執行**：AGENTS.md（規範性を保ちつつ人間可読に）・method.md・charter.md・
  DoD.md・template-copy.md・README.md 人間地図・learnings 導入・スキル導線を刷新。`doc_standards` に**造語
  denylist 検査**（金メッキ→提案・関門/門番 の不統一など）を足し、review スキルに観点を追加。verify 緑。

## 受け入れ基準（完了条件）
- `uv run verify` 全成功（`doc_standards` 込み）。
- 人が `docs/README.md` から全正本文書へ辿れる（孤立ゼロ）。各正本文書が可視の平易な導入で始まる。
- 造語は用語集で標準用語に対応づく。`doc_standards` が孤立・凡例欠落・用語集不整合・最悪造語を検出する
  ことを回帰テストで固定（maker≠checker のレビュー済み）。日付レビュー note は `docs/archive/` に移動。
