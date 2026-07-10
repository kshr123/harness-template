---
id: T-0179
kind: task
status: todo
title: T-0176〜T-0178 の独立レビューを通し、指摘を反映する
created: 2026-07-10
depends_on: [T-0178]
verified_by: []
---
# T-0179 独立レビュー（T-0176〜T-0178）

## なぜ要るか
完了は「`uv run verify` の成功」と「重大な問題でブロックされていないこと」の**両方**で確定する。
T-0176〜T-0178 は verify を通しただけで、確かめる側を通していない。作った本人（同じ文脈のエージェント）は
自分で合否を判定しない。

直前の実績：T-0169〜T-0172 の独立レビューは、verify が緑のまま通していた**本物の欠陥**（初回昇格が
NaN を止めない）と、作業記録の誇張を見つけた。レビューは形式ではない。

## 対象
- `c1a7b1e` T-0176（`gates.py` の fail closed・`GateResult.params`・`evaluate` の ValueError 化）
- `e1b24e9` T-0177（`Registry(require_source=True)`）
- `bdfa870` T-0178（造語の是正・AGENTS の条文・review スキルの手順）

## 深さ（review スキルの規約より）
`src/`・`tests/` に触れるので **full**：別モデルで独立レビュー＋**ミューテーション**（新しく入れた
guard を実際に壊して対象テストが赤くなることを実測）。壊す対象は少なくとも次の 4 つ。
- `value_threshold` / `change_threshold` の `math.isfinite` を外す（両方）
- `change_threshold` の候補未測定・baseline 不在の分岐順
- `Registry.register` の `require_source` 判定
- `_run` の `inspect.signature(...).bind`（未知の引数が TypeError に戻ること）

## とくに確かめてほしいこと
1. **T-0178 で新しく導入した review スキルの手順（新しく現れた名前の列挙）を、この差分自身に適用する。**
   `params`・`not_finite`・`threshold_not_met`・`baseline_not_finite`・`require_source`・`source` は
   それぞれ出典を答えられるか。答えられないものは造語。
2. `GateResult.params` を `Mapping[str, Any]` にしたことで、frozen dataclass の等価比較・ハッシュに
   問題が出ないか（現状ハッシュしていないが、将来 set に入れると壊れる）。
3. `not_finite` を `value_threshold` にも入れたのは挙動変更である。`inf` を良い値として使う指標が
   `METRICS` / `AGENT_METRICS` に無いことを確かめる（あれば退行）。
4. `evaluate` の `inspect.signature(factory).bind(ctx, **params)` は、`ctx` を位置引数として束ねている。
   将来 `GATES` に `ctx` を第 1 引数に取らない判定を登録できてしまわないか。

## 受け入れ基準
- 独立レビューの判定が出ている（問題なし、または指摘を反映して問題なし）。
- ミューテーション 4 件がすべて赤になることを実測した記録がある。
- 指摘を反映したうえで `uv run verify` 全成功。
