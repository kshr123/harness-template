---
id: T-0178
kind: task
status: done
title: 残った造語を消し、造語を作らせない決まりごとをレビュー観点に置く
created: 2026-07-10
depends_on: [T-0177]
verified_by:
  - tests/test_coverage_lint.py::test_real_repo_all_cli_commands_are_reachable
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0178 造語の是正と再発防止

## 何が起きたか
T-0172 で判定の名前を標準用語（`value_threshold` / `change_threshold`）へ直したが、
受け入れ基準を `grep -rn 関門` で書いたため、**同じ意味の言い換え**が 10 か所生き残った。

- `絶対条件` / `相対条件`（docs/agent.md・ds-code.md・agent-code.md・ops.md・スキル 2 件）
- `絶対（…）と相対（…）`（docs/ds.md・templates/ci/retrain.yml）— 複合語ですらないので語の検索では捕まらない

## 破り方は 2 種類しかない
1. **名前が無い概念に名前を付ける**（`関門` の初出。`work/EP-06/DESIGN.md` の設計時）。
2. **既にある概念に 2 つ目の名前を作る**（docs が `value_threshold` を「絶対条件」と言い換えた）。
   改名すると、言い換えた側だけが取り残される。

## 対策（作り込まない）
- **1 は機械で塞ぐ**：`Registry(require_source=True)` で出典なしの登録を `ValueError`（T-0177・実装済み）。
  ただし出典の**中身が本物か**は機械には分からない。書き忘れを不可能にするだけ。
- **2 は機械では塞げない**：禁止語の一覧は既に作られた語しか知らず、次の新語を必ず見逃す。
  代わりに「言い換えを作らない」を決まりごとにし、**レビューの手順に確かめられる質問**を置く：
  「この差分で新しく現れた名前を列挙し、それぞれの出典を答えよ。答えられないものは造語」。
  差分を見れば列挙できるので、これは「気をつける」ではなく手順になる。
- **生成表は作らない**。写しを機械で維持するより、写しを置かない方が単純。docs は判定の意味を書き写さず、
  登録済みの名前をそのまま使い、一覧は `uv run gates` を指す。写しが無ければ腐らない。

## 受け入れ基準
- docs・スキル・templates・src・tests に `絶対条件` / `相対条件` / `関門` が無い
  （AGENTS.md の「使ってはいけない例」としての引用と、`docs/archive/`・`work/` の当時の記録は除く）。
- `uv run gates` への導線がスキルと正本 docs にある（coverage_lint が通る）。
- AGENTS.md に「概念に 2 つ目の名前を作らない」があり、review スキルに列挙の手順がある。
- `uv run verify` 全成功。

## やらないこと
- 禁止語の機械検査（後追いにしかならない・自分で不良を作って出口で検査する形になる）。
- doc_sync の一般化と用語表の生成（写しを増やしてから維持する構造になる）。
