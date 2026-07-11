---
id: T-0187
kind: task
status: done
title: 決まりごとを撤回する経路を作る（追加しかできない仕組みは、効かない規則を溜める）
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_retraction_lint.py::test_residue_in_asset_is_flagged
  - tests/test_retraction_lint.py::test_empty_retracted_is_green
  - tests/test_retraction_lint.py::test_word_boundary_avoids_substring_false_positive
  - tests/test_retraction_lint.py::test_allowed_places_are_not_residue
  - tests/test_retraction_lint.py::test_empty_reason_raises
---
## 実装（done）
- 条文：AGENTS.md の原則に「決まりごとは手段＝効かない決まりごとは撤回する」を追加（撤回の是非は人・
  記録先は docs/learnings.md・残骸は機械が検査）。
- 検査：`src/harness/retraction_lint.py`（core・PM_CHECKS）。撤回した名前の有限一覧 `RETRACTED`（理由必須）を
  1 か所に置き、資産（src/docs/skills/templates）に語境界一致で残れば error。名前を挙げてよいのは撤回一覧と
  docs/learnings.md の 2 か所だけ。空一覧＝正常（緑）。掃除が済めば項目を消してよい（増える一方でない）。
- docs/core.md にモジュール行を追加＋doc-sync で自動生成表を更新。
- 受け入れ基準を満たす：名前を仕込むと error（実測・test_residue_in_asset_is_flagged）／空でも緑
  （test_empty_retracted_is_green）／理由必須（test_empty_reason_raises）／語境界で部分一致を除外。

# T-0187 決まりごとの撤回の経路が無い

## 何が問題か
この基盤は「作業で得た気づきを `docs/learnings.md` に記録し、価値があれば機械検査・抽象・スキル・規約の
どれかに落とし込む」という**追加の流れ**だけを設計している。落とし込んだものを**外す流れ**が無い。

結果として、撤回漏れが実在した。DEC（決定記録）の仕組みは EP-26 で廃止されたのに、識別子と参照が
コード・文書・スキルに残り、T-0165 で一掃するまで気づかれなかった。`issues/ISS-0015` も同じ形
（モジュールを消したのに、それを指す文書の行が残る）。

決まりごとは目的ではなく手段である。効かなくなった手段を外せないなら、手段は増える一方になる。

## 何をするか（2 つに分ける。混ぜない）
### 1. 条文（AGENTS.md）
「決まりごとは手段であって目的ではない。効かないと分かった決まりごとは、追加したときと同じ手順で
**撤回する**」を原則に足す。撤回の記録先は `docs/learnings.md`（「何を・なぜ・いつ外したか」）。
撤回の判断は人の判断であり、機械にはさせない。

### 2. 撤回漏れの検査（ここだけ機械化する）
撤回した仕組みの名前は、撤回した時点で**有限に確定する**（DEC・`decisions/`・…）。これは L-017 が
禁じた「まだ作られていない不良を当てにいく検出器」ではなく、**既に確定した集合が消えたことの確認**
である。同じ形の検査は既にある（`doclint` の ID 接頭辞の置き場実在検査）。

撤回した名前を 1 か所に置き、それが `src/` `docs/` `.claude/skills/` `templates/` に残っていたら
verify を失敗にする。この一覧は「増える」のではなく、掃除が済めば**その項目を消してよい**
（残骸が消えたことを一度証明したら、検査は役目を終える）。

## 受け入れ基準
- 撤回した名前を 1 つ仕込むと `uv run verify` が失敗する（実測。仕込んだら戻す）。
- 撤回の一覧が空でも検査は緑（空の一覧は正常な状態）。
- AGENTS.md に撤回の条文がある。撤回の記録先が `docs/learnings.md` であることが書かれている。
- `uv run verify` 全成功。

## やらないこと
- 撤回の是非を機械に判定させない（「この規則はもう効いていない」は人の判断）。
- 禁止語の一覧を作らない（L-017。撤回した**識別子**の一覧と、造語の禁止語一覧は別物。前者は確定した
  有限集合、後者は未来の語を当てにいく無限集合）。
