---
id: T-0302
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
  - tests/test_lintkit.py::test_word_bounded_matches_standalone_name_not_substring_or_path
  - tests/test_lintkit.py::test_validate_exemptions_requires_a_reason
  - tests/test_lintkit.py::test_corpus_parse_caches_and_tolerates_syntax_error
  - tests/test_lintkit.py::test_rule_from_callable_preserves_behavior_and_derives_name_summary
---
# T-0302 P0：lintkit 共有基盤（未結線）

`src/harness/lintkit/` を新設し、自前テストで固める。まだどの検査も載せ替えない（挙動変更ゼロ＝verify 緑）。

- `ids.py`：ID・プレースホルダ・語境界の文法（`ISS-\d+`・work/ 参照・`L-###`・`XXXX|0000`・`word_bounded`）。
- `exempt.py`：理由必須・fail-closed の免除表 `Exemptions`（4 か所の重複の統合先）。
- `corpus.py`：root・相対パス（`as_posix`）・ast 解析キャッシュ（1 ファイル 1 回・構文エラーは None）。対象集合・
  散文抽出は、それを最初に使うフェーズ（P3/P4）で足す（投機的に作らない）。
- `__init__.py`：`Rule`（name/summary/scan）＋`run`＋`Rule.from_callable`（既存 InvariantCheck の包み＝移行の足場）。

lintkit は `profile.py` を持たない下位ディレクトリなので code_doc_lint の中核走査（`src/harness/*.py` 直下）の
対象外＝core.md への記載は不要。プロファイル境界も不変（core→core の import のみ）。
