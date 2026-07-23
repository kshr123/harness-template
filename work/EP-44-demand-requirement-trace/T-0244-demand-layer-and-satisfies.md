---
id: T-0244
kind: task
status: done
title: 要求層 docs/demands を足し REQ の satisfies→DEM 参照を task-lint で検査する
created: 2026-07-23
closed: 2026-07-23
depends_on: []
verified_by:
  - tests/test_pm.py::test_req_satisfies_dangling_demand_is_error
  - tests/test_pm.py::test_req_satisfies_existing_demand_is_ok
  - tests/test_pm.py::test_missing_demands_dir_is_ok
  - tests/test_pm.py::test_satisfies_without_demands_dir_is_error
  - tests/test_pm.py::test_malformed_satisfies_is_error
---
# T-0244 要求層と satisfies 参照検査

## なぜ
既存は要件↔作業↔検証（REQ→work→verified_by）の鎖はあるが、その上流「どのクライアント要求から来たか」が無い。
コンサルの説明責任（何を約束し何を満たしたか）には要求→要件のトレースが要る。標準 ISO/IEC/IEEE 29148 は要求
（StRS）と要件（SyRS/SRS）を分ける。要件と同型の軽量ファイル＋参照検査で足す（重い専用モデルは作らない）。

## 何を
- `docs/demands/DEM-*.md`＋雛形 `.harness/templates/demand.md`。REQ 雛形に `satisfies: []` を追記。
- `pm.py`：`DEMANDS_DIR` 定数＋`pm.lint` に satisfies 参照検査（REQ frontmatter を読み、`satisfies` の各 DEM が
  `docs/demands/` に実在するか。要求層が無い案件は検査しない＝任意）。
- `init_project.CASE_AREA_ROOTS`＋`_REMOVE_GLOBS` に `docs/demands`／`docs/demands/DEM-*` を追加。EP-42 の
  「宣言 ⊆ 定数」「doc AREAS ⊇ 定数」検査が template-copy.md の AREAS 追随を強制した（drift 機構が働いた）。
- `AGENTS.md` にトレースの鎖（DEM→REQ→work→検証）を明記。dogfood：`DEM-001`＋`REQ-001` の satisfies。

## 検証
`uv run verify` 緑（自リポの実 DEM/REQ 鎖も通る）。`test_req_satisfies_dangling_demand_is_error`＝実在しない DEM を
satisfies＝error、`test_req_satisfies_existing_demand_is_ok`＝実在 DEM は通る、`test_missing_demands_dir_is_ok`＝
要求層が無い案件は検査しない。maker≠checker（別 fable）で差分確認。
