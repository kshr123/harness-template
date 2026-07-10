---
id: T-0179
kind: task
status: done
title: T-0176〜T-0178 の独立レビューを通し、指摘を反映する
created: 2026-07-10
closed: 2026-07-10
depends_on: [T-0178]
verified_by:
  - tests/test_gates.py::test_value_threshold_rejects_a_non_finite_value
  - tests/test_gates.py::test_change_threshold_rejects_a_non_finite_candidate_even_without_a_baseline
  - tests/test_gates.py::test_change_threshold_names_a_non_finite_baseline_distinctly
  - tests/test_gates.py::test_evaluate_rejects_an_unknown_gate_parameter_as_a_value_error
  - tests/test_registry.py::test_a_vocabulary_registry_refuses_a_name_without_a_source
  - tests/test_promotion_characterization.py::test_ds_a_non_finite_metric_never_becomes_champion
  - tests/test_promotion_characterization.py::test_agent_a_non_finite_metric_never_becomes_champion
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

## 結果（2026-07-10・別モデルの独立レビュー・別 worktree）
**判定：問題なし**（完了をブロックする重大な問題は無し）。

### ミューテーション（指定 4 件＋レビュアーが足した 2 件。すべて RED）
| 壊した箇所 | 落ちたテスト | 結果 |
| --- | --- | --- |
| `value_threshold` の `math.isfinite` を除去 | `test_value_threshold_rejects_a_non_finite_value` | RED |
| `change_threshold` の候補側 `math.isfinite` を除去 | gates 1 件＋characterization 2 件 | RED |
| `change_threshold` の baseline 側 `math.isfinite` を除去（追加） | `…names_a_non_finite_baseline_distinctly` | RED |
| 「候補未測定・有限性」より先に「baseline 不在」を見る順へ入替 | gates 2 件＋characterization 2 件＋store/models 各 1 件 | RED |
| `Registry.register` の `require_source` 判定を無効化 | registry 1 件＋gates 2 件 | RED |
| `_run` の `inspect.signature(...).bind` を除去（追加） | `…rejects_an_unknown_gate_parameter_as_a_value_error` | RED |

緑のまま通ったミューテーションは無い。

### 新しく現れた名前と出典（review スキル手順 3 の自己適用）
`params`（`inspect` の parameters と同語）・`not_finite`（`math.isfinite` の否定）・
`threshold_not_met`（threshold は tfma.MetricThreshold・not met は状態の記述）・
`baseline_not_finite`（既存 `baseline_not_measured` と同型の合成）・`require_source`・`source`。
出典を答えられない名前は無し＝**造語なし**。出典文字列そのものも実在を確認
（TFMA の `GenericValueThreshold` / `GenericChangeThreshold`、MLflow 2.9 以降の champion alias、
SageMaker の `ModelApprovalStatus`）。

### 個別の確認
- `value_threshold` への `not_finite` 追加は退行でない。`METRICS` 23 件と `AGENT_METRICS` 2 件を実測し、
  `inf` を良い値として使う指標は無い（大きいほど良い側はすべて上限有界、小さいほど良い側は下限 0）。
- `GateResult.params` は frozen だがハッシュ不能（実測 `TypeError: unhashable type: 'dict'`）。
  等価比較は正常。今ハッシュする呼び手は無い。→ T-0185。
- `ctx` を第 1 引数に取らない判定を `GATES` に登録でき、`bind(ctx, **params)` が `ctx` を別の引数へ
  位置束縛して**黙って走る**（実測）。現登録の 2 判定は正しいので実害は無い。→ T-0185。

## 完了の根拠
上記 6 件のミューテーションが RED になることを実測し、`uv run verify` は全成功。重大な指摘は無し。
軽微な指摘 2 件は完了をブロックしないので、独立したタスク（T-0185）に切り出した。
