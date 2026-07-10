---
id: T-0189
kind: task
status: done
title: 目的を正本に書く（手段の言葉で目的を書かない）
created: 2026-07-10
closed: 2026-07-10
depends_on: []
verified_by:
  - tests/test_purpose.py::test_agents_states_the_purpose_before_the_principles
  - tests/test_purpose.py::test_readme_states_the_purpose
  - tests/test_purpose.py::test_agents_names_the_three_levels_of_guarantee
  - tests/test_purpose.py::test_agents_says_repo_checks_do_not_prevent_tampering
  - tests/test_doc_source_lint.py::test_real_repo_durable_docs_have_no_work_refs
---
# T-0189 目的を正本に書く

## 何が問題だったか
`README.md` と `AGENTS.md` は、この基盤が何のためにあるかを**手段の言葉**で書いていた
（「品質は仕組みで担保する」「完了は verify で判定する」「作る側と確かめる側を分ける」）。

その結果、目的から逆算しようとした 5 本の独立した設計レビューが、全員**手段から手段を導いた**。
誰も「資産が案件へどう渡り、どう戻るか」を見なかった。見たら、複製手順そのものが壊れていた
（手順どおりに複製すると緑になる状態が存在しない）。

オーナーの指摘：「その目的、手段では？」

## やったこと
`AGENTS.md` の冒頭に「目的」節を置き、最上位を **「案件を重ねるほど強くなること」** と定めた。
`README.md` にも同じ目的を 1 段落で置いた（README はテンプレートとして複製されるので、複製先で最初に読まれる）。

目的を成り立たせる 4 条件を、手段でなく**結果の言葉**で書いた。

1. 出す答えが黙って間違っていないこと
2. 間違えたときに、何を間違えたか特定して戻せること
3. 人の時間は、判断が本当に人のものである場所だけに使う（**ゼロを目標にしない**）
4. 案件で得たものが次の案件へ渡り、案件で得た改良が本体へ戻ること

3 番目は独立レビューの指摘を取り込んだ。「人の時間ゼロ」を目標に書くと、**基準を書かないことが目的に適合する**。
実際、`goal.yaml` の `thresholds` 書き忘れでどんな出力も合格する欠陥は、この誤った定式の症状だった（T-0197）。

2 番目も同じく、レビューが「復旧の次元が無い」と指摘して足したもの。切り戻しの手段が長らく存在しなかった
（`rollback` は `src/` `docs/` 全体で 0 件）のは、目的に「戻せること」が書かれていなかったからである（EP-33）。

## 併せて書いたこと
- **保証の 3 段階**（(a) 構造的に不可能 / (b) 機械が検出 / (c) 人が気をつける）と、
  **(b) を名乗ってよい条件**（対象集合が構文・型・登録から機械的に導ける。書く人の申告に依存するなら (c)）。
- **リポジトリの中の検査は「事故防止」であって「改竄防止」ではない**。`checks.py` を編集する手は
  `checks.toml` を編集する手と同じで、中に不動点は無い。止まるのは独立レビューと、作業ツリーの外
  （branch protection・required checks）だけ。この区別を書いておかないと、リポ内の検査に過剰な期待をする。

## 受け入れ基準
- `AGENTS.md`・`README.md` に目的が書かれ、手段（verify・maker-checker）がその従属物として位置づけられている。
- 造語を作らない（既存の語だけで書く）。用語表に依存せず単独で読める。
- `uv run verify` 全成功。
- **目的の文が消えたら赤くなる**（`tests/test_purpose.py`）。目的は消しても他のどの検査も赤くならない場所に
  あったので、そこだけ留めた。対象は 2 ファイル固定なので、書く人の申告に依存しない。
