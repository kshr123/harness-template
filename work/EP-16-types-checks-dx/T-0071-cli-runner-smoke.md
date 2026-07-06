---
id: T-0071
kind: task
status: done
title: CliRunner スモーク＝data サブコマンドを typer 経由で end-to-end に叩く
created: 2026-07-06
depends_on: [T-0066]
verified_by:
  - tests/test_cli_smoke.py::test_catalog_commands_exit_zero_with_representative_item
  - tests/test_cli_smoke.py::test_help_lists_all_subcommands
  - tests/test_cli_smoke.py::test_list_and_lint_run_in_project_root
  - tests/test_cli_smoke.py::test_experiments_with_empty_results_dir_exits_zero
  - tests/test_cli_smoke.py::test_predict_without_required_options_fails
---
# T-0071 CliRunner スモーク

## 背景
既存 `test_catalog.py` はコマンド関数を**直接**呼ぶだけで、typer の配線（コマンド登録・引数解析・exit code）は
通っていない。`data predict`/`data experiments` 等の Option 解析や未登録コマンドの取りこぼしを end-to-end で止める。

## 受け入れ基準（typer.testing.CliRunner）
- 新規 `tests/test_cli_smoke.py`：`from typer.testing import CliRunner` と `harness.ds.cli.data_app` を使い、
  カタログ系（`blocks`/`encoders`/`models`/`metrics`/`sources`/`selectors`/`tuners`/`unsupervised`/`list`/`lint`）を
  CliRunner で叩き **exit_code == 0**・出力に代表項目（columns/logreg/roc_auc/selectkbest/random 等）が載ることを確認。
  `data --help` に全サブコマンド（predict/experiments 含む）が載ることも確認。
- 引数を要する `data experiments --results <空dir>`（空 → 案内メッセージ・exit 0）と `data predict`（引数不足 → exit≠0）を
  CliRunner で 1 本ずつ（重い store 準備が要るものは既存 integration テストに任せ、ここは配線の smoke に絞る）。
- 層マーカー（integration＝CLI 結線）。lint/list は make_project の一時プロジェクトで（既存の cli テストの流儀に倣う）。

## 触ってよいファイル
新規 `tests/test_cli_smoke.py`。`cli.py` は呼ぶだけ・編集しない（並行作業あり）。必要な変更が出たら報告。

## 検査（テスト先書き・構成から導く）
- 各カタログコマンドの exit_code==0＋代表項目の存在（レジストリ登録から導ける）。
- `data --help` に predict/experiments/selectors/tuners が載る（配線の証拠）。
- `data experiments --results <空>` → exit 0・「実験結果が無い」。`data predict`（--work 等欠落）→ exit≠0（typer の必須引数）。

## 独立レビュー（2026-07-06・maker≠checker）
配線が本当に typer 経由（CliRunner）で叩かれ・exit_code と出力の両方を検査・内部例外は exit 1 に落ちるため
握りつぶし不可・代表項目はレジストリ定義から導出（金メッキ無し）を実測で確認。minor 2 件を反映：`--help` の登録検査を
全 18 コマンド（invoke で叩けない store 依存の profile/compare/cluster/embed/anomaly/saved を含む＝ここでしか登録漏れを
検出できない）に拡大・assert 失敗時に `result.exception` を出す。

## 結果
実装・独立レビュー（--help 全網羅・例外表示を反映）・verify 緑で done。ideal-build-plan Wave 4「CliRunner スモーク」。
