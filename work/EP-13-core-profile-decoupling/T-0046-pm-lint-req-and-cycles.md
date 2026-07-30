---
id: T-0046
kind: task
status: done
title: pm.lint 強化（REQ 実在・未カバー要件・depends_on 循環検出）
created: 2026-07-05
verified_by:
  - tests/test_pm.py::test_dangling_requirement_is_error
  - tests/test_pm.py::test_existing_requirement_is_ok
  - tests/test_pm.py::test_uncovered_requirement_is_info
  - tests/test_pm.py::test_no_requirements_at_all_is_ok
  - tests/test_pm.py::test_depends_on_cycle_is_error
  - tests/test_pm.py::test_acyclic_depends_on_chain_is_ok
  - tests/test_pm.py::test_requirement_filename_with_suffix_matches_id
  - tests/test_pm.py::test_deep_dependency_chain_does_not_crash
---
# T-0046 pm.lint 強化

## 受け入れ基準
- `item.requirements` の REQ が `docs/requirements/REQ-*.md` に実在しなければ **error**（depends_on と同型・同様式）。
  （当初は「`docs/requirements/` が無い場合は素通り」だったが、EP-48 T-0283 で satisfies と対称の fail-closed に
  改めた＝要件文書が無くても非空の `requirements` は参照エラー。要件を 1 つも書かない案件は従来どおり素通り。）
- どの単位からも参照されない REQ は **info**（未カバーの要件・失敗にはしない）。
- `depends_on` の循環（A→B→A）を DFS で検出し **error**（実在検査では拾えない）。
- 既存の木モデル・lint 挙動は不変（加算のみ）。実 work/ ツリーは従来どおり lint 緑。

## 結果
実装・テスト先書き（pre-fix で 3 件失敗）・独立レビュー・verify 緑で完了予定。`docs/ideal-build-plan-2026-07-05.md` Wave 1。
