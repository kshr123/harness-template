---
id: T-0067
kind: task
status: done
title: ExperimentSpec（pydantic v2・extra=forbid）で実験 config を型付け＋threshold→decision_threshold
created: 2026-07-06
depends_on: [T-0052]
verified_by:
  - tests/test_experiment_spec.py::test_current_config_shape_validates
  - tests/test_experiment_spec.py::test_unknown_top_level_key_typo_rejected
  - tests/test_experiment_spec.py::test_unknown_variant_key_typo_rejected
  - tests/test_experiment_spec.py::test_threshold_string_value_rejected
  - tests/test_experiment_spec.py::test_empty_variants_rejected
  - tests/test_experiment_spec.py::test_decision_threshold_is_not_a_config_key
  - tests/test_experiment_spec.py::test_optional_keys_are_captured_not_ignored
  - tests/test_ds_experiment.py::test_decision_threshold_renamed_and_reaches_eval
  - tests/test_experiment_holdout.py::test_decision_threshold_renamed_and_reaches_eval
---
# T-0067 ExperimentSpec（実験 config の型付け）

## 背景（ISS-0007）
`.harness/config.toml`・テーブル定義は pydantic v2（extra=forbid）で締めているのに、実験 YAML だけ型無し
＝config 駆動を掲げる自己矛盾。`thresholds`（合否辞書）と `threshold`（決定境界 float）が兄弟で共存し取り違えても
検知できず、未知トップキーは黙って無視。エージェントが config をコピペ改変する前提なので実損に直結する。

## 受け入れ基準（pydantic v2・既存 config.py/issues.py の書き方に合わせる）
- `ExperimentSpec`（`model_config = ConfigDict(extra="forbid")`）で実験 config を型付け。現行 config.yaml の構造を忠実に：
  `seed:int, n:int, n_folds:int, data:{kind,...}, target:str, model:{kind,...}, variants:{名前:{features:[...], encode?:[...]}},
  test_mode?:{n?,n_folds?}, thresholds:{指標:float}` ＋ optional `task/metrics/stratify_by/order_by/id_column/decision_threshold`。
  ネストも extra=forbid（typo を止める）。variants は 1 つ以上・各 variant は features 1 つ以上。置き場所は core か ds か
  自然な方（実験は ds プロファイル寄り＝`src/harness/ds/experiment.py` か新 `ds/experiment_spec.py`）。
- **`threshold`→`decision_threshold` に改名**：`run_experiment`・`final_eval_on_holdout` の引数名を変え、決定境界であることを名前で示す
  （`thresholds` 合否辞書との混同を断つ）。**呼び手（train.py 雛形・tests）を全て更新**（grep して漏れなく）。metric_fn_for へは
  内部で `threshold=` として渡す（eval 側の evaluate は threshold 名のまま＝そちらは別レイヤ）。
- **train.py 雛形**：config.yaml を読んだ後 `ExperimentSpec.model_validate(...)` で検証してから使う（未知キー・型違いを起動時に止める）。
  decision_threshold を使う箇所を更新。experiment スキル（`.claude/skills/experiment`）の config 説明に decision_threshold と型付けを反映。

## 触ってよいファイル
`src/harness/ds/experiment.py`（or 新 `experiment_spec.py`）＋雛形 train.py＋`.claude/skills/experiment/*`＋対応テスト
（`tests/test_ds_experiment*.py`・`tests/test_experiment_holdout.py`・新 `tests/test_experiment_spec.py`）。
`eval.py`/`cv.py`/`pipeline.py`/`models.py` は触らない（呼ぶだけ・並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 正しい config（現行 config.yaml 相当）→ model_validate 通過。**未知トップキー**（例 `thresold: ...`）→ ValidationError。
  ネストの未知キー（variant に `feature:` typo）→ ValidationError。thresholds に非 float → ValidationError。variants 空 → error。
- `run_experiment(..., decision_threshold=0.4)` が効く（旧 `threshold=` は無い＝TypeError で使えない＝改名の証拠）。
- train.py `--test` スモークが通り results を書く（e2e・既存の e2e テストが緑）。decision_threshold 経路で挙動不変。

## 独立レビュー（2026-07-06・maker≠checker）
改名の完全性（run_experiment/final_eval_on_holdout の両方・旧 threshold= は TypeError）と型の締まり（未知キー・型違い・
取り違え本丸 decision_threshold に合否辞書＝全て ValidationError）を実測で確認。important 1 件を反映：Spec が受理するのに
train.py が読まない optional キー＝「正当キーの黙殺」（ISS-0007 の失敗様式の再発）→ train.py を**検証済み spec 経由に
書き換え**、`metrics/stratify_by/order_by/id_column` を run_experiment/final_eval_on_holdout へ実際に流す。`decision_threshold`
は config キーでなく関数引数（雛形は OOF から選ぶ）なので **Spec から外し**、config に書くと extra=forbid で起動時エラーに。
SKILL も是正。minor（strict の非対称・死んだ fallback）は spec 経由化で解消。

## 結果
実装・独立レビュー（optional キーを実際に流す・decision_threshold を config から外す）・verify 緑で done。
ISS-0007 消化＝promoted_to。ideal-build-plan Wave 4。
