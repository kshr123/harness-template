---
id: T-0002
kind: task
status: done
title: CI とコミット前検査
requirements: [REQ-001]
depends_on: [T-0001]
owner: sakurada
closed: 2026-07-18
verified_by:
  - tests/test_ci_config.py::test_ci_uses_the_shared_verify_command
  - tests/test_ci_config.py::test_ci_runs_verify_on_linux_and_windows
  - tests/test_guardrails.py::test_secrets_scan_wired
---
# T-0002 CI とコミット前検査

## 目的
ローカルと CI が同じ共通の検証コマンド（uv run verify）を使い、完了の定義を一致させる。

## 受け入れ基準（満たしている）
- `uvx pre-commit run --all-files` にすべて成功する（`.pre-commit-config.yaml` にフック一式。gitleaks・
  actionlint・check-jsonschema・commit-msg-lint。配線の生死は test_guardrails が常在検査）。
- CI（.github/workflows/ci.yaml）が uv run verify を実行する（`test_ci_uses_the_shared_verify_command`）。

## 状態（2026-07-18・実態に合わせて done に）
このマーカーは EP-01 期の骨組みで、受け入れ基準の実体は後続の複数 epic が納品済みだった：CI verify の
配線と OS matrix（EP-16）、破壊的 git deny・秘密情報検出の pre-commit＋CI 同一入口（EP-20）、CI verify の
雛形（EP-21）、pre-commit への actionlint／check-jsonschema 委譲（EP-25）。受け入れ基準を確かめるテストが
既に verify に載っている（上の verified_by）ので、todo のまま残すのは実態と食い違う＝done に更新した。
