---
id: T-0294
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-49]
verified_by:
  - tests/test_code_doc_lint.py::test_reverse_stale_bullet_row_is_error
  - tests/test_code_doc_lint.py::test_reverse_scoped_to_the_docs_own_directory
  - tests/test_conventions.py::test_real_conftest_errors_on_slow_without_iss
---
# T-0294 windows verify を緑に（パス区切り・stdio エンコード）
Windows の verify が 3 テストで落ちる（いずれも移植性バグ・deliver とは無関係）：
- `code_doc_lint` の逆向き検査が `directory/module` を `relative_to` の生 str で出す＝Windows で `\` 区切りになり、
  テストの `src/harness/...`（`/`）と一致しない → `as_posix()` に直す（リポ相対パスは常に `/` で言う）。
- `test_conventions` の pytester サブプロセスが conftest の非 ASCII エラー文言を cp932 で出し、テストが utf-8 で
  読んで UnicodeDecodeError → conftest の stdout/stderr を utf-8 に固定（cli.py と同じ作法。`_REAL_CONFTEST` は
  実 conftest そのものなので、実行時とサブプロセスの両方が直る）。

## 受け入れ基準
- [ ] code_doc_lint の逆向き指摘のパスが常に `/` 区切り（プラットフォーム非依存）。
- [ ] conftest が stdout/stderr を utf-8 に固定し、非 ASCII 文言のサブプロセス出力が読める。
- [ ] 対応する既存テスト（reverse 系・conventions のサブプロセス系）が緑。
