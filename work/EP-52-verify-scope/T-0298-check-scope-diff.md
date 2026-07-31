---
id: T-0298
kind: task
status: done
closed: 2026-07-31
start: 2026-07-31
due: 2026-07-31
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_scope.py::test_docs_only_runs_invariants_only
  - tests/test_scope.py::test_verification_infrastructure_forces_full
  - tests/test_scope.py::test_unclassified_source_forces_full
  - tests/test_scope.py::test_profile_source_scopes_to_that_profile
  - tests/test_scope.py::test_non_profile_test_file_runs_just_that_file
---
# T-0298 `uv run check --scope diff`（変更に応じた参考実行）
新モジュール `src/harness/scope.py` が git 差分から実行計画を決める。`check --scope diff`（既定 `all` は従来どおり
byte 一致）で呼ぶ。**参考実行＝done の証拠にしない**（完了は `uv run verify` の全成功だけ）。振り分け：不変条件は
毎回全部（安く・横断的）／散文だけ→言語ツールもテストも回さない（Chrome も pytest も）／プロファイルの
ソース・テスト→そのプロファイルの `test_globs` だけ／中核・検査インフラ（checks.py・conftest・pyproject 等）・
分類できない変更→全実行（fail-closed の過近似）。影響グラフは新設せず既存の `Profile.test_globs` を使う。

## 受け入れ基準
- [x] 散文だけの変更→不変条件のみ（ruff/mypy/pytest/Chrome を回さない）。
- [x] 検査インフラ・中核・分類できない変更→全実行に落ちる（fail-closed）。
- [x] プロファイルのソース・テスト変更→そのプロファイルのテストだけに絞る。
- [x] 中核テストの変更→その 1 本だけ回す。
- [x] `verify`（scope=all）は従来どおり完全実行のまま。
