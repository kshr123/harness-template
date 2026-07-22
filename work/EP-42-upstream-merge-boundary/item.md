---
id: EP-42
kind: epic
status: done
plan: detailed
created: 2026-07-22
closed: 2026-07-22
requirements: []
depends_on: []
---
# EP-42 本体→案件の merge が案件領域を汚染する穴を塞ぐ

オーナーの「全体見直してプロジェクトマネジメントに必要な事柄は？」を受け、fable にプロジェクト全体を通しで
棚卸しさせた。結論：単一案件の PM は完了の定義・学習の機械化で世間標準を超えており足すものはほぼ無い。弱いのは
ポートフォリオ層（最上位目的「案件を重ねるほど強くなる」そのもの）で、その正体は「還流が無い」ではなく
（還流手順は EP-31 実装済み）、**本体→案件の継続 merge がテンプレートの自己適用と構造的に矛盾している**こと
だった。fable の指摘を scratch git で独立再現して確定：fork が `git merge upstream/main` すると、本体側の作業
単位（work/EP-99）が案件の work/ に無音流入し、init-project で消した単位を本体が変更していれば modify/delete で
復活する。clone-simulation CI は fork の瞬間しか見ておらず、fork 後の時間発展（2案件目の初回 merge）が無検査。
これは条件1（黙って汚染しない）×条件4（蓄積）の交点で、この基盤にとって最も痛い型の欠陥。

## 変更（T-0242）
- `docs/template-copy.md`：2 節の偽の主張（「案件領域は merge で競合しない」）を訂正し、本体も work/issues を持つ事実
  と汚染経路を明記。4 節に、merge 後 案件領域を fork(HEAD) の版へ統一する復旧レシピ（対象集合は init-project の
  白紙化対象＝正本は init_project.py）を実測済みで記載。5 節に還流候補を洗う git ワンライナー（台帳を作らない）。
- `tests/test_template_copy.py`：fork→本体前進→merge を実際に git で再生し、案件領域が fork 側のまま・本体改良だけ
  入ることを検査（保証 (b)。散文の手順が退行すれば赤くなる）。
- `.claude/skills/harvest`：還流候補ワンライナーを1行追記。
- `src/harness/init_project.py`：scrub の取りこぼし修正＝`INV-*`（調査単位）を白紙化対象に追加（取りこぼすと fork に
  前案件の調査が残る）。テストにも INV の白紙化を追加。

## 作らなかったもの（fable の再点検で維持）
見積り・期日・ADR復活・リスク重大度・worktree二重着手ロック・merge鮮度の門番（時間で赤くなる検査の再発明）。
`reflux --list` 的コマンドは fork が回り始めてから（今は消費者ゼロ・ワンライナーで足りる）。
