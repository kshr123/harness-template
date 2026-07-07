---
id: T-0136
kind: task
status: done
title: ドキュメントを自完結に（用語集・機械検査 doc_standards・DEC-0019 を撤去し、造語は初出で平易に説明）
created: 2026-07-07
depends_on: [T-0132]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0136 ドキュメントを本文だけで読めるようにする（用語集と機械化を撤去）

## 背景（オーナーのフィードバック 2026-07-07）
EP-24 で用語集（`docs/glossary.md`）と機械検査（`doc_standards`）を作ったが、オーナーの意図と逆だった：
「**そもそも造語を使わず、誰が読んでも本文だけで分かる説明・構成にしてほしい**。用語集はどうしても必要なら
可だが、最新に保つ負荷がかかる。機械化してほしいのではなく、ドキュメントを書くときのルールでしかない」。
→ 用語集への依存と機械化を撤去し、各文書を**自完結**（別ファイルを引かずに読める）にする。

## やること
1. **機械化の撤去**：
   - `src/harness/doc_standards.py` と `tests/test_doc_standards.py` を削除。
   - `src/harness/checks.py` の `PM_CHECKS` から `doc_standards.run_checks` と import を除く。
   - `docs/decisions/DEC-0019-documentation-standards.md` を削除。
2. **用語集の撤去**：`docs/glossary.md` を削除。
3. **本文の自完結化**：各文書の `[語](glossary.md#…)` リンクを、**初出でその場に平易な一文の説明**を置く形に
   置き換える（2 回目以降はリンク無しの素の語）。造語はできるだけ**平易な言い換え**にする：
   - 例：`[正本](glossary.md#正本)` → 「唯一の正とする置き場（正本）」。以降は「正本」。
   - 例：`[導線](glossary.md#導線)` → 「使い方に人が辿り着けるリンク」。造語「導線」を無理に残さない。
   - 例：`[champion](glossary.md#champion)` → 「champion（現在採用している版）」。標準語は残してよいが初出で一言。
   - 例：`[金メッキ](…)` → 「実装の出力をそのままコピーした期待値（入力から導けない）」。
   - 対象ファイル：`docs/agent.md`・`docs/serve.md`・`docs/ops.md`・`docs/method.md`・`docs/charter.md`・
     `docs/DoD.md`・`docs/template-copy.md`・`docs/learnings.md`・`README.md`・`AGENTS.md`・
     `.claude/skills/{serve,agent,review}/SKILL.md`。
   - **AGENTS.md は規範を 1 つも弱めない**（意味保持・リンクを外して素の語＋必要なら一言に置換するだけ）。
4. **索引の整理**（`docs/README.md` は人間向けの地図として残す＝場所が分かるのは良いこと）：
   - 文書地図から `glossary.md` の行を削除、読む順から用語集の項目を削除。
   - 末尾の「doc_standards が機械的に検出…」段落と DEC-0019 へのリンクを削除。
   - `docs/archive/README.md` の「doc_standards の対象外」等の機械検査への言及を削除（ただの保管庫の説明に）。
5. **review スキル**：T-0132 で足した「ドキュメント観点」節（DEC-0019 参照）を削除（機械・プロセス化しない。
   書き方は担当が気をつける範囲）。

## 受け入れ基準
- `uv run verify` 全成功（`doc_standards` 撤去後も緑。doclint が DEC-0019/glossary への dead link を出さない
  ＝参照を漏れなく消せた証拠）。
- どの文書も**本文だけで読める**（glossary.md を開かずに造語の意味が分かる）。`glossary.md` / `doc_standards`
  / `DEC-0019` への参照がリポジトリから消えている（`grep -r glossary.md docs *.md .claude` が 0 件）。
- AGENTS.md の各ルールが保持されている（HEAD と条ごとに突き合わせて確認）。

## 触ってよい範囲
上記に挙げたファイルと、`src/harness/checks.py`・削除する 4 ファイル・この item.md。CLAUDE.md は変えない。
コード（doc_standards 以外）・他プロファイルには触れない。
