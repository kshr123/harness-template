---
id: T-0052
kind: task
status: done
title: holdout 最終評価の結線（OOF で選抜→holdout で一度だけ確認・fixed_split/holdout_indices に入口）
created: 2026-07-06
depends_on: [T-0051]
verified_by:
  - tests/test_experiment_holdout.py::test_holdout_metrics_follow_holdout_composition
  - tests/test_experiment_holdout.py::test_holdout_with_inverted_rule_scores_zero
  - tests/test_experiment_holdout.py::test_fit_uses_only_df_fit_rows
  - tests/test_experiment_holdout.py::test_overlapping_ids_raise
  - tests/test_experiment_holdout.py::test_id_type_mismatch_raises
  - tests/test_experiment_holdout.py::test_null_id_raises
  - tests/test_experiment_holdout.py::test_multiclass_holdout_via_task
---
# T-0052 holdout 最終評価の結線（ISS-0004）

## 設計判断（この結線で確定する・DEC-0010 に基づき前倒し）
- **段取り**：全行 OOF（`run_experiment`）で**選抜/合否**を決め、最後に**触っていない holdout（test）で一度だけ最終評価**する。
  holdout は選抜・閾値調整に**使わない**（使うとリーク）。champion 確定後の 1 回だけ。
- これで `data.fixed_split` と `cv.holdout_indices`（今は入口の無い孤立部品）に入口ができる（DEC-0009 を満たす）。

## 受け入れ基準
- `experiment.py` に `final_eval_on_holdout(estimator, df_fit, y_fit, df_holdout, y_holdout, *, task, threshold, metrics)`
  （名前は要検討可）を新設：estimator を **df_fit だけ**で 1 回 fit → df_holdout で予測 → `eval.evaluate`/`metric_fn_for`
  で指標を返す（`HoldoutResult` dataclass 可）。多クラス（T-0051）も task 経由で通す。
- **リーク・ガード**：df_fit と df_holdout の id が重なっていたら ValueError（黙って評価しない）。holdout 行は fit に
  一切入らないことを検査で固定。
- experiment スキル（`.claude/skills/experiment`）と雛形 train.py（`work/EP-06-.../code/train.py` を参照に）に「OOF で選抜→
  holdout で一度だけ最終評価→results/ に記録」の 1 段を追記（人とエージェントが段取りを迷わない）。
- 既存 `run_experiment` の挙動は不変（holdout は独立の関数として足す・回帰ゼロ）。

## 触ってよいファイル
`src/harness/ds/experiment.py`＋対応テスト（`tests/test_experiment*.py`）、`.claude/skills/experiment/*`、雛形 train.py。
`eval.py`/`cv.py`/`pipeline.py`/`registry.py`/`models.py` は**呼ぶだけ・編集しない**（多クラスの独立レビュー進行中）。
必要な変更が出たら編集せず報告する。

## 検査（テスト先書き・構成から導く）
- holdout を train と別構成（例：holdout だけ符号反転や別平均）にし、holdout 指標が train OOF と別値になることを構成から確認。
- fit に holdout 行が入っていないこと（fit 後の学習データ数＝df_fit 行数）。
- id 重複で ValueError。

## 独立レビュー（2026-07-06・maker≠checker）
リーク構造・金メッキ無しを実測で確認（clone 非破壊・holdout を選抜/閾値に使っていない・exit code は OOF のみ）。
important 1 件：id の**型不一致**（int 30 と str "30"）で set の重なり検出が黙って無効化＝リーク・ガード素通り。
→ 型が違えば ValueError で停止（+ 欠損 id も明示メッセージで停止＝minor も同時対応）。回帰テスト 2 本追加。
minor（predict の明示上書き口が holdout 側に無い非対称）は据え置き（規約内で問題化しない）。

## 結果
実装・独立レビュー（型不一致ガード反映）・verify 緑で done。ISS-0004 を消化＝promoted_to。
