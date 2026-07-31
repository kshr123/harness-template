---
id: T-0307
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
  - tests/test_lintkit.py::test_workflows_trigger_names_across_shapes
  - tests/test_ci_lint.py::test_retrain_template_missing_schedule_flagged
  - tests/test_agent_schedule_lint.py::test_missing_schedule_trigger_is_error
---
# T-0307 P5：GitHub Actions の on: True-trap を lintkit.workflows に集約

pyyaml は YAML 1.1 で `on:` キーを bool `True` に読む。この落とし穴の吸収を、ops の `ci_lint` と agent の
`schedule_lint` がそれぞれ別に持っていた（片方だけ直すと全 workflow が trigger 無し誤検知になる drift の温床）。

- 新設 `src/harness/lintkit/workflows.py`：`on_block(doc)`（True-trap 込みの読み）・`trigger_names(doc)`。
- `ci_lint._trigger_names` は `workflows.trigger_names` へ委譲、`schedule_lint` の `on:` 読みは `workflows.on_block` へ。
- 両プロファイルは lintkit（core）を import＝profile→core 方向で境界不変。挙動は byte 一致（ci_lint・schedule_lint の
  旧テストを 1 行も変えず緑＝挙動不変の証明）。`steps`/`run_commands` は ci_lint 固有（consumer 1 つ）なので移さない。
