---
id: T-0171
kind: task
status: done
title: 昇格判定を中核の GATES レジストリへ抽出する（文言は据え置き）
created: 2026-07-10
depends_on: [T-0170]
verified_by:
  - tests/test_gates.py::test_value_threshold_uses_a_lower_bound_when_higher_is_better
  - tests/test_gates.py::test_value_threshold_uses_an_upper_bound_when_lower_is_better
  - tests/test_gates.py::test_value_threshold_is_fail_closed_for_nan
  - tests/test_gates.py::test_value_threshold_treats_an_unmeasured_metric_as_a_failure
  - tests/test_gates.py::test_change_threshold_requires_a_strict_improvement_by_default
  - tests/test_gates.py::test_change_threshold_normalizes_improvement_by_direction
  - tests/test_gates.py::test_change_threshold_min_change_is_the_same_sign_for_both_directions
  - tests/test_gates.py::test_change_threshold_is_fail_closed_for_nan_on_either_side
  - tests/test_gates.py::test_change_threshold_passes_when_there_is_no_baseline
  - tests/test_gates.py::test_change_threshold_fails_when_the_baseline_lacks_the_metric
  - tests/test_gates.py::test_evaluate_collects_every_failure_not_just_the_first
  - tests/test_gates.py::test_evaluate_is_approved_only_when_every_gate_passes
  - tests/test_gates.py::test_evaluate_rejects_an_unknown_gate_kind
  - tests/test_gates.py::test_every_gate_is_registered_with_a_description_from_its_docstring
  - tests/test_promotion_characterization.py::test_ds_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_agent_only_a_strict_improvement_promotes
---
# T-0171 昇格判定の抽出

## 何が重複していたか
「champion を差し替えてよいか」の判定が 3 か所に写されていた。

- `ds/eval.py` の `passes` と `agent/eval.py` の `passes`（閾値の判定。ロジックは同一、参照するレジストリと
  エラー文言だけが違う）。
- `ds/models.py` の `promote_model` と `agent/store.py` の `promote_agent`（現 champion との比較）。

## 抽出したもの（`src/harness/gates.py`）
- `GATES` レジストリ（中核）。項目は `value_threshold` と `change_threshold` の 2 つ。config は `kind` の
  文字列で選ぶ。カタログは `uv run gates`。
- `GateContext` … 候補の metrics・現 champion の metrics・**解決済みの向き**。中核はプロファイルの
  指標レジストリを import しない（向きを解決するのは呼び手の責務のまま）。
- `evaluate(ctx, specs) -> PromotionDecision` … 判定を**全件集めてから**合否を出す（`PM_CHECKS` と同じ方式）。
  最初の 1 件で止めると、直した次の実行でまた別の条件に落ちる往復が起きる。
- `PromotionDecision.approved` / `PromotionError` … `approved` / `rejected` は SageMaker Model Registry の
  `ModelApprovalStatus` の語彙。

## 決めたこと
- **レジストリにする**。判定は開いた集合（公平性・推論の遅延・データ量の下限・人手の承認・ベイズの収束診断が
  控えている）。閉じたデータ構造にすると、判定を足すたびに中核の型を編集することになりプロファイル境界を破る。
- **`change_threshold` の改善量は向きで正規化する**（大きいほど良いなら候補−baseline、そうでなければ
  baseline−候補）。だから `min_change` の符号は指標の向きに依存しない：`log_loss` でも `min_change=0.01` は
  「0.01 以上下がること」。既定は `0.0` で厳密な不等号＝**同点は不合格**（既存の仕様と同じ）。
- **`baseline` は必須の引数**にして `"champion"` だけを受ける。「何と何を比べるのか」が config の 1 行から
  必ず読める（将来 `"previous_version"` を足す拡張点にもなる）。
- 判定はすべて fail closed。合格条件を正の形で問うので NaN はどの比較も False になる。測っていない指標も不合格。

## 等価であることの証拠
文言（「絶対関門で不合格」「相対関門で不合格」）は**一字一句そのまま**にした。だから
**既存のテストを 1 文字も変更せずに全部緑になる**ことが、抽出が挙動を変えていない機械的な証拠になる
（`git status --porcelain tests/` に現れるのは新規の `tests/test_gates.py` だけ）。文言の是正は T-0172 で行う。

## 用語の出所
`value_threshold` / `change_threshold`＝TensorFlow Extended の `tfma.MetricThreshold`。
`approved` / `rejected`＝Amazon SageMaker Model Registry の `ModelApprovalStatus`。
`champion`＝MLflow Model Registry の alias（2.9 で Model Stages を非推奨にした後の推奨）。

## 受け入れ基準
- 既存テストが**無変更で**全成功する（`git diff` に `tests/test_ds_models.py` 等が現れない）。
- `GATES` の 2 項目が docstring 1 行目つきで `uv run gates` に載る。
- `gates.py` の import が stdlib と `harness.registry` だけ（中核がプロファイルに依存しない）。
- `uv run verify` 全成功。
