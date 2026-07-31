---
id: T-0304
kind: task
status: done
created: 2026-07-31
closed: 2026-07-31
start: 2026-07-31
due: 2026-07-31
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_boundary_lint.py::test_core_subpackage_import_of_profile_is_error
  - tests/test_boundary_lint.py::test_profile_dir_files_are_not_treated_as_core
---
# T-0304 boundary_lint を中核サブパッケージまで広げる（P0 が開けた死角を塞ぐ）

独立レビュー B1：lintkit（中核初のサブパッケージ・profile.py なし）を足した瞬間、`boundary_lint._core_modules`
が `src/harness/*.py` 直下しか見ないため、`src/harness/lintkit/*.py` の `import harness.ds` が**黙って通る**
死角ができた（＝検査機構における条件①違反）。

- `_core_modules` を `src/harness/**/*.py` から profile.py を持つディレクトリ配下を除いた集合へ（直下＋中核
  サブパッケージ）＝対象集合を機械的に導く（(b) の作法）。
- 相対 import はファイルの所属パッケージ（`_package_of`＝`harness.lintkit` 等）を起点に解決（サブパッケージ内の
  `from ..ds import x` も正しく判定）。免除鍵とメッセージは `src/harness` からの相対パス（直下は従来どおり
  ファイル名なので既存の免除・テストは不変）。
