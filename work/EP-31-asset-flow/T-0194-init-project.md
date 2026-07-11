---
id: T-0194
kind: task
status: done
title: uv run init-project（複製後の初期化を 1 コマンドに）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0193]
verified_by:
  - tests/test_init_project.py::test_scrub_empties_project_area_and_keeps_core
  - tests/test_init_project.py::test_scrub_is_idempotent
  - tests/test_init_project.py::test_cli_refuses_before_fork_and_deletes_nothing
  - tests/test_init_project.py::test_cli_scrubs_when_forked
  - tests/test_init_project.py::test_scrub_sets_profiles_and_preserves_comments
---
# T-0194 init-project

## 何を
複製後の初期化（案件領域の白紙化＋profiles 設定）を実行可能な 1 コマンド `uv run init-project` にする。
手作業 4 歩は「読み忘れ・やり忘れ」という発生源を持つので、コマンドに集約して発生源を封じる。

## 設計
- 判定の芯は純関数（`is_forked`・`blocking_reason`）、git の副作用は `list_remotes` に隔離、白紙化は
  `scrub`（べき等・案件領域だけ）。CLI は `--force` か確認プロンプトを必須にする。
- 安全装置：`upstream` リモートが無い（未 fork＝本体そのもの）状態では**拒否**する（本体の誤爆防止）。

## 受け入れ基準
- 案件領域だけが白紙化され、本体領域は不変（test で固定）。べき等。未 fork では拒否。
- `uv run verify` 全成功。
