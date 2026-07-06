---
id: T-0079
kind: task
status: done
title: 雛形 train.py の task 分岐（regression/multiclass の --test スモーク・G7）
created: 2026-07-06
depends_on: [T-0078]
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_regression_smoke
  - tests/test_e2e_experiment.py::test_e0001_multiclass_smoke
---
# T-0079 雛形 train.py の task 三値対応

## 背景（G7）
実験雛形 `work/EP-06-ds-experiment-loop/E-0001-interaction-feature/code/train.py` が閾値選択で task 分岐しない
（L168-170 付近：無条件に `select_threshold_max_f1`＋二値 `evaluate`）。task: regression / multiclass の config を書くと
ここで大声で落ちる＝「雛形をコピーして config だけ書き換える」流儀が三値で成立していない（DEC-0009 の入口が三値で壊れている）。
雛形は e2e が毎回実行する正本（DEC-0009）なので、雛形が三値で通ってこそエージェントが config だけで三種を回せる。

## 受け入れ基準
- train.py が `spec.task`（binary|multiclass|regression）で分岐：
  - binary＝従来（閾値選択＋二値評価）不変。
  - regression＝閾値選択せず回帰指標で評価（final_eval_on_holdout の回帰経路を使う）。
  - multiclass＝閾値選択せず多クラス指標で評価。
- **既存の binary e2e が不変で緑**（既定 config は binary のまま）。
- regression・multiclass の `--test`（小スモーク）が通る（新しい config 変種＝設定ファイルで持つ・雛形本体は 1 つ）。
  e2e（`uv run verify` の e2e 段）に regression/multiclass スモークが接続され、雛形の三値対応が機械で守られる。

## 触ってよいファイル
`work/EP-06-ds-experiment-loop/E-0001-interaction-feature/`（train.py＋config 変種＋必要なら results）＋
`tests/test_e2e_experiment.py`（実在名は確認・e2e の接続）。`src/harness/**` は触らない（部品側は T-0078 で対応済み前提）。

## 検査（テスト先書き・構成から導く）
- 既存 binary e2e が不変で緑。
- regression config で train.py --test が exit 0・回帰指標が results に残る（小さな線形合成で妥当）。
- multiclass config で train.py --test が exit 0・多クラス指標が残る。
- 期待値は config とデータ構成から導く（金メッキ禁止）。

## 独立レビュー（maker≠checker・差分のみ・実測）
異常なし。binary e2e 不変（4 passed）・regression/multiclass を実走し task 別指標・threshold 有無・多クラス OOF 3 クラス出現を実測。
期待値（rmse≈雑音 std・r2≈0.96・class 比率・flip 率）を n=20 万シミュで独立検証＝金メッキでない。変異 3/3 撃墜（分岐を潰すと
sklearn 側で fail-loud・argmax 外すと schema 検証で fail-loud）。DATA_SOURCES.register は重複で fail-loud・src 未変更。
