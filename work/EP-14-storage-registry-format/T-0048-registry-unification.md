---
id: T-0048
kind: task
status: done
title: 9 レジストリを Registry/Entry に統一＋汎用カタログ＋data sources
created: 2026-07-05
verified_by:
  - tests/test_registry.py::test_description_derived_from_docstring_first_line
  - tests/test_registry.py::test_register_without_description_or_docstring_raises
  - tests/test_registry.py::test_class_factory_does_not_inherit_parent_docstring
  - tests/test_registry.py::test_duplicate_kind_is_rejected
  - tests/test_registry.py::test_resolve_unknown_kind_lists_candidates_and_catalog_and_extra_hint
  - tests/test_registry.py::test_mapping_protocol
  - tests/test_registry.py::test_build_calls_factory_with_seed_and_params_dropping_wiring_keys
  - tests/test_registry.py::test_build_rejects_task_mismatch
  - tests/test_registry.py::test_metric_entry_carries_fields_and_fn_alias
---
# T-0048 レジストリ統一＋汎用カタログ

## 受け入れ基準
- `harness/registry.py`（core）に `Entry`（factory/description/task/tags）・`MetricEntry`・`Registry`
  （Mapping 互換・`register`/`resolve`/`build`）。description は docstring 1 行目から自動導出（無ければ登録時 ValueError＝DEC-0009）。
  クラス工場は親 docstring を継承しない。
- MODELS/ENCODERS/BLOCKS/METRICS/CLUSTERERS/DIMRED/ANOMALY/TS_MODELS/DATA_SOURCES を定数名を保ったまま
  Registry 化。既存の build_* 呼び出しは動作不変（同じ部品を作る）。
- CLI に `render_catalog` を 1 本・各 `data <一覧>` はそれを呼ぶだけに。**`data sources` を新設**（DATA_SOURCES の入口・DEC-0009 の隙間を塞ぐ）。

## 結果
実装（registry 変換・カタログ・data sources）・テスト先書き（test_registry 9 本）・独立レビュー・verify 緑で完了予定。
`docs/ideal-build-plan-2026-07-05.md` Wave 2。ISS-0008 消化。
