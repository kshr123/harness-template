---
id: T-0196
kind: task
status: done
title: 還流の手順を決める（単位・判断者・基準）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0193]
verified_by:
  - tests/test_template_copy.py::test_template_copy_defines_reflux_procedure
---
# T-0196 還流の手順

## 何を
harvest スキルの 1 文を具体化し、案件→本体（還流）の手順を template-copy.md に定める：
- **単位＝本体領域だけに触る 1 コミット**（`git cherry-pick` / PR で運べる）。
- **還流するのは learnings そのものでなく、ルール化の結果**（検査・部品・スキル・規約）。
- **判断者＝テンプレート側の独立レビュー**（案件のエージェントは PR を起こすところまで）。
- **回数で待たない**（「2 案件で役立ったら」の回数基準を廃し、一般性で判断＝AGENTS/method に統一）。

## なぜ
還流の経路が無ければ蓄積が本体に戻らず、「案件を重ねるほど強くなる」が成立しない。harvest の
「2 つ以上の案件で役立ったものだけ」は回数基準で AGENTS と矛盾していたので廃す。

## 受け入れ基準
- template-copy.md が還流の単位・判断者・基準（回数によらない）を定義し、harvest がそこへリンクする。
- `uv run verify` 全成功。
