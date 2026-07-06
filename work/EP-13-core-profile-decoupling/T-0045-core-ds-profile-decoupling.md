---
id: T-0045
kind: task
status: done
title: core→ds のプロファイル分離（data CLI 移動・profiles 機構・checks 脱ds）
created: 2026-07-05
verified_by:
  - tests/test_profiles.py::test_load_profiles_returns_ds_profile_for_this_repo
  - tests/test_profiles.py::test_empty_profiles_means_core_only
  - tests/test_profiles.py::test_bogus_profile_module_raises_clear_error
  - tests/test_profiles.py::test_module_without_profile_raises_clear_error
---
# T-0045 core→ds のプロファイル分離

## 受け入れ基準
- `data` の CLI（`data_app`＋`_data_*`＋`data_main`）を `harness/ds/cli.py` へ移動。`[project.scripts]` の
  `data = "harness.ds.cli:data_main"`。中核 CLI（status/task-lint/check/verify/issue/changelog）は `harness/cli.py` に残す。
- `harness/profiles.py`：`Profile(name, pm_checks)`＋`load_profiles(root)`（config の `profiles=[...]` を import）。
  import 失敗・PROFILE 不在は明示エラー。`harness/ds/profile.py` に `PROFILE = Profile("ds", (schema.data_lint,))`。
- `config.HarnessConfig.profiles: list[str]`（既定空＝core 単体で動く）。`.harness/config.toml` に `profiles = ["harness.ds"]`。
- `checks.py` から `from harness.ds import schema` を除去し、`PM_CHECKS` を「中核＋プロファイルの pm_checks」の組み立てに。
  本リポでは data_lint が従来どおり走る。`template-copy.md` を「config の 1 行を消す」に更新。

## 結果
実装・独立レビュー・verify 緑で完了予定。`docs/ideal-build-plan-2026-07-05.md` Wave 1・DEC-0010。core↔ds 境界が実装でも一致。
