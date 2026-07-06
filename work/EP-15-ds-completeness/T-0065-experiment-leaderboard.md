---
id: T-0065
kind: task
status: done
title: 実験リーダーボード（data experiments＝results の metrics を集約した構造化表）
created: 2026-07-06
depends_on: [T-0052]
verified_by:
  - tests/test_experiment_leaderboard.py::test_leaderboard_aggregates_and_sorts_descending
  - tests/test_experiment_leaderboard.py::test_leaderboard_union_columns_fills_null
  - tests/test_experiment_leaderboard.py::test_leaderboard_mixed_int_float_metric_coerces_not_crash
  - tests/test_experiment_leaderboard.py::test_leaderboard_non_numeric_metric_raises_with_filename
  - tests/test_experiment_leaderboard.py::test_leaderboard_nan_metric_sorts_last
  - tests/test_experiment_leaderboard.py::test_leaderboard_missing_dir_raises
  - tests/test_experiment_leaderboard.py::test_leaderboard_broken_yaml_raises_with_filename
  - tests/test_experiment_leaderboard.py::test_cli_experiments_smoke
---
# T-0065 実験リーダーボード

## 背景
1 実験は変種ごとに `results/metrics_<variant>.yaml`（variant・metrics・passed・model.version・fingerprints）を残すが、
横串で見る入口が無い。results を集約した構造化表（人は marimo・エージェントは表）で「どの変種が勝ったか」を一目にする。

## 受け入れ基準（polars ネイティブ・構造化表の流儀＝eval の *_table と同じ）
- `experiment.py` に `leaderboard(results_dir: Path, *, sort_by: str | None = None) -> pl.DataFrame`：
  - `results_dir` 直下の `metrics_*.yaml` を全部読む（yaml.safe_load）。各ファイルから variant・passed・model.version・
    metrics（flatten：各指標名→列）を 1 行に。指標が変種で違っても和集合の列（無い所は null）。
  - `sort_by`（指標名）指定時はその指標で降順、未指定は最初に見つかった指標で降順（安定・決定的）。空ディレクトリは空表
    （列だけ or 空）。壊れた yaml・metrics 欠落は分かる ValueError か skip（設計を選び docstring 明記）。
- `cli.py` に `data experiments`（typer）：`--results <dir>`（必須）[`--sort-by <指標>`] → `leaderboard` を呼び表を print
  （既存 render/表示の流儀に合わせる）。DATA_SOURCES/カタログ同様の入口（DEC-0009）。

## 触ってよいファイル
`src/harness/ds/experiment.py`（leaderboard）＋`src/harness/ds/cli.py`（data experiments）＋
`tests/test_experiment*.py`・`tests/test_cli_*.py`（新規可）。`pipeline.py`/`eval.py`/`cv.py`/`models.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- results_dir に 2〜3 の `metrics_<v>.yaml` を手で構成（variant・metrics・passed・model.version）→ `leaderboard` の表が
  変種ぶんの行・指標ぶんの列を持ち、sort_by の指標で降順（構成した値の大小から順序を導く）。
- 変種で指標集合が違う構成 → 和集合の列・欠けは null。
- 空ディレクトリ → 空表（落ちない）。壊れた yaml の扱い（選んだ設計どおり）。
- CLI スモーク（CliRunner か関数直呼び）で表が出る・exit 0。

## 独立レビュー（2026-07-06・maker≠checker）
決定性（ファイル順・列順・和集合・タイ安定）・実在 results（work/EP-06）での動作・エッジ（空/壊れ/不正 sort_by）を実測で確認。
important 1：指標値の int/float 混在（yaml で `1` は int）で polars 構築が TypeError＝契約（ファイル名入り ValueError）から外れる
→ 指標値を float 正規化し、非数値は「どのファイル・どの指標か」を含む ValueError。minor：NaN 指標を最下位へ（優勝に見せない）・
存在しないディレクトリを空表と区別して ValueError・CLI は全行表示（tbl_rows=-1）・passed 非真偽値/variant を型正規化。回帰テスト 4 本追加。

## 結果
実装・独立レビュー（型正規化・NaN 最下位・dir 検査・全行表示を反映）・verify 緑で done。
ideal-build-plan Wave 3「experiment leaderboard」。EP-15 の実装タスクの最後。
