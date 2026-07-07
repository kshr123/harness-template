---
id: T-0130
kind: task
status: done
title: 骨組み＝人間向け索引・用語集・DEC-0019・doc_standards（孤立/凡例/用語集整合）・日付noteをarchiveへ
created: 2026-07-07
depends_on: []
verified_by: [tests/test_doc_standards.py::test_real_repo_doc_standards_is_green, tests/test_doc_standards.py::test_unlinked_doc_is_error_until_linked]
---
# T-0130 ドキュメント刷新の歩く骨組み（発見可能性＋仕組みの土台）

## 狙い
端まで通る最小の骨組みを先に作る：人間向けの入口（索引）・用語集・標準の正本（DEC）・検査の土台
（`doc_standards`）を置き、`uv run verify` を緑にする。プロースの本格書き換えは T-0131/0132。

## 作るもの
1. **`docs/README.md`（人間向け索引）**：
   - 冒頭に平易な What/Why（この基盤は何で、なぜ在るか）を 3〜5 文。専門語は使わない or その場で説明。
   - **読む順（reading path）**：初見の人が読む順序（例 charter → method → 各プロファイル）。
   - **ID・略語の凡例**：`EP`/`T`/`E`/`INV`/`DEC`/`ISS`/`REQ` と `PSI`/`CV`/`CT`/`PII`/`PM` を 1 行ずつ。
   - **文書地図**：`docs/` 直下と主要文書を Diátaxis の 4 分類（Tutorial/How-to/Reference/Explanation）で表にする。
     `docs/*.md` すべて（archive を除く）へのリンクを含める（＝孤立ゼロの起点）。
2. **`docs/glossary.md`（用語集）**：造語・内部用語→平易な定義＋標準用語（英/カナ）。最低限、監査で挙がった
   主要語を網羅：正本, 導線, 入口, 作業単位/item, 歩く骨組み(walking skeleton), 昇格(規則の昇格 / モデルの
   champion 昇格＝**二義を分けて定義**), 金メッキ(＝入力から導けないハードコード期待値), 門番/関門/gate(＝
   ブロッキング vs 助言・絶対/相対ゲート＝統一), band(severity band: stable/warning/alert), 指紋/fingerprint,
   来歴/lineage, harness, profile, champion, shadow deployment, champion/challenger, cassette(record-replay),
   effort, loops(trigger×stop×policy), fail-closed/fail-open, PSI, coverage_lint/doclint/deploy_lint 他 lint 群,
   maker-checker, ratchet, 案件(project/engagement), verify。各項目 1〜3 行・定義は初見で分かる平易さ。
3. **`docs/decisions/DEC-0019-documentation-standards.md`**（`_template.md` の型に従う）：ドキュメント標準を
   正本化。Diátaxis の 4 分類／標準用語（Google style: jargon は初出で定義 or 用語集リンク）／各正本文書は
   可視の平易な導入で始める（HTML コメントに隠さない）／発見可能（索引から辿れる）／過不足なく簡潔。
   機械化する部分と review 観点で担保する部分の線引きを明記。参考リンク（diataxis.fr, Google style, Vale）。
4. **日付レビュー note を退避**：`docs/ds-review-2026-07-05.md`・`docs/ideal-build-plan-2026-07-05.md`・
   `docs/structure-review-2026-07.md` を `docs/archive/` へ `git mv`。`docs/archive/README.md` に「日付付きの
   作業メモの保管庫（正本ではない・索引の孤立検査の対象外）」と 1 行ずつの由来。
5. **`src/harness/doc_standards.py`（新検査・core）**：`run_checks(root) -> list[pm.Problem]`。この段階では
   **即満たせる検査だけ**を実装（導入 lede 検査と造語 denylist は T-0131/0132 で足す）：
   - **孤立検査**：`docs/*.md`（直下・非再帰。`docs/README.md` 自身と `docs/archive/**` は除外）が
     `docs/README.md` の本文からリンク（相対パス出現）されていること。未リンク＝error。理由必須 allowlist
     `_EXEMPT`（coverage_lint と同型・空理由は ValueError）。
   - **凡例網羅**：`docs/**/*.md`（archive 除く）で使われている ID 接頭辞（`EP|T|E|INV|DEC|ISS|REQ`）が
     `docs/README.md` の凡例に載っていること。載っていない接頭辞が使われていたら error。
   - **用語集整合**：`docs/glossary.md` が存在し、見出し項目（用語）に重複が無く、各項目に定義本文が
     ある（空見出し＝error）。
   - stdlib のみ（tomllib 等）。重い依存・ネットワーク無し。`from harness import pm` は可。
   - `checks.py` の `PM_CHECKS` に `doc_standards.run_checks` を追加（coverage_lint の隣）。
6. **`docs/README.md` を索引に加える導線**：README.md（ルート）から `docs/README.md` へのリンクを 1 行足す
   （人間の入口を発見可能にする）。

## テストの要点（`tests/test_doc_standards.py`・期待値は構成から導出）
- 一時プロジェクトに `docs/README.md`＋`docs/foo.md` を置き、README が foo にリンクしない→foo が孤立 error。
  リンクを足す→消える。`_EXEMPT` に理由つきで入れると消える／空理由は ValueError（他 lint と同型）。
- `docs/bar.md` で `DEC-0007` を使うが README 凡例に `DEC` が無い→error。凡例に足すと消える。
- `docs/glossary.md` に重複見出し／空見出し→error。
- **現リポ回帰**：`doc_standards.run_checks(REPO_ROOT)` が空（現リポの索引・用語集・凡例が整合＝緑）。
- markers（unit/integration）必須。

## 触ってよい範囲
`docs/README.md`・`docs/glossary.md`・`docs/decisions/DEC-0019-*`・`docs/archive/`（＋3 note の移動）・
`src/harness/doc_standards.py`・`src/harness/checks.py`（PM_CHECKS への 1 行追加）・`tests/test_doc_standards.py`・
`README.md`（docs/README への 1 行）・この item.md。既存 docs 本文の**大規模書き換えはしない**（T-0131/0132）。
