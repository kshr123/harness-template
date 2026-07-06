---
id: T-0047
kind: task
status: done
title: 保存 4 作法を core storage.py に抽出（store/models/schema を薄く）
created: 2026-07-05
verified_by:
  - tests/test_storage.py::test_atomic_write_commits_and_returns_fingerprint
  - tests/test_storage.py::test_atomic_write_cleans_tmp_and_reraises_on_failure
  - tests/test_storage.py::test_resolve_uri_file_scheme_maps_under_root
  - tests/test_storage.py::test_resolve_uri_rejects_non_file_scheme
  - tests/test_storage.py::test_manifest_roundtrip_with_japanese_values
  - tests/test_storage.py::test_verify_fingerprint_passes_match_and_rejects_mismatch
  - tests/test_storage.py::test_schema_project_dir_fails_loud_on_non_file_metadata_uri
---
# T-0047 保存 4 作法を core storage.py に抽出

## 受け入れ基準
- `harness/storage.py`（core・stdlib＋yaml のみ）に `resolve_uri`／`fingerprint`（`hashlib.file_digest`）／
  `atomic_write`（tmp→replace・失敗時は tmp を消して再送出）／`write_manifest`／`read_manifest`／`verify_fingerprint`。
  manifest のバイト形式は現行と同一（`yaml.safe_dump(allow_unicode=True, sort_keys=False)`）。
- store.py・models.py・schema.py はこれを呼ぶ薄い方針層に（各自の検証・昇格関門・split 再書き込み拒否・
  manifest-last の印は据え置き）。models.py は sklearn/yaml/hashlib を import しない状態を維持。
- 非 `file:` URI は 3 箇所とも fail-loud（`UnsupportedURIError`）。schema の黙示フォールバックは廃止（docstring に明記）。

## 結果
実装・テスト先書き・独立レビュー・verify 緑で完了予定。`docs/ideal-build-plan-2026-07-05.md` Wave 2・DEC-0011（予定）。ISS-0006 消化。
