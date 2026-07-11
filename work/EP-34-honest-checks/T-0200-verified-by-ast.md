---
id: T-0200
kind: task
status: done
title: verified_by に テスト名 を必須化し、実在照合を grep から ast へ
requirements: [REQ-001]
created: 2026-07-11
depends_on: []
verified_by:
  - tests/test_pm.py::test_verified_by_file_only_is_error
  - tests/test_pm.py::test_verified_by_unrelated_real_file_is_error
  - tests/test_pm.py::test_verified_by_comment_only_test_is_error
  - tests/test_pm.py::test_verified_by_string_literal_named_test_is_error
  - tests/test_pm.py::test_verified_by_class_method_form_is_ok
  - tests/test_pm.py::test_verified_by_class_method_missing_is_error
  - tests/test_pm.py::test_verified_by_parametrized_id_matches_base_name
  - tests/test_pm.py::test_verified_by_missing_named_test_is_error
  - tests/test_pm.py::test_verified_by_present_named_test_is_ok
---
# T-0200 verified_by の実在照合を本物にする

## 実測した欠陥（再現済み）
`pm.py` の完了↔検証の結びつけは、`verified_by` の `::テスト名` をファイル本文への素朴な `\b名前\b`
正規表現で照合していた。したがって：
- `# TODO: test_acceptance を書く予定` というコメント行だけのファイルで、`::test_acceptance` を指す done
  が通る（コメントに名前が現れるだけで一致してしまう）。
- `::` を書かなければ実在照合は一切走らず、「実在する無関係なファイル」でも通る。

この欠陥は実際に踏まれた（実在しないテスト名を書いた事故・テスト改名に追随しなかった事故）。

## 直したこと
- **`::テスト名` を必須化**した。ファイル名だけの `verified_by` は error（`_verified_by_problems`）。
- 実在照合を **ast** に変えた（`_collectable_test_names`）。数えるのは実際の定義だけ：モジュール直下の
  関数定義（`def test_x` → `"test_x"`）と、クラス名・クラス内メソッドの `"TestClass::test_y"` 形。
  文字列・コメントは当たらない。
- **クラス内メソッドの nodeid 形（`<ファイル>::<クラス>::<メソッド>`）に対応**した。参照の chain を `::`
  で連結して照合する。パラメータ化の `[...]` は各節から落とす（`test_a[case1]` → `test_a`）。
- **既存の `verified_by` を移行**した：`::` 無しの「ファイル名だけ」の形は 15 件（すべて task の done）
  あった。各ファイルに実在する代表テストを ast で確認して `::テスト名` を付けた（下記）。指すテストが
  存在しなかった作業単位は **0 件**（15 件すべて、対象ファイルに実在する定義へ結べた）。
- 移行後、リポジトリ全体の `::` 付き `verified_by` は 589 箇所。新しい ast 照合で赤くなった既存エントリは
  **0 件**（全件、指す先が def として実在した）。

## 移行した 15 件（ファイル名だけ → ::代表テスト）
- T-0001 → `tests/test_pm.py::test_render_status_counts_leaves`
- T-0003 → `tests/test_ds_data.py::test_splits_do_not_overlap_and_cover_all`
- T-0004 → `tests/test_ds_eval.py::test_metrics_registry_covers_classification_and_regression`
- T-0005 → `tests/test_config.py::test_reads_file_and_layer_override`
- T-0006 → `tests/test_pm.py::test_investigation_done_requires_conclusion`
- T-0007 → `tests/test_issues.py::test_open_issue_is_ok_and_appears_in_pending`
- T-0008 → `tests/test_ds_schema.py::test_load_schemas_reads_template_scope`
- T-0009 → `tests/test_structure.py::test_new_structure_layout`
- T-0084 → `tests/test_ds_models_onnx.py::test_binary_roundtrip_matches_sklearn`,
  `tests/test_catalog.py::test_formats_have_descriptions`
- T-0085 → `tests/test_serve_app.py::test_health_returns_status_and_model_version`,
  `tests/test_serve_cli.py::test_serve_cli_passes_app_and_host_port_to_uvicorn`
- T-0086 → `tests/test_serve_deploy_lint.py::test_real_repo_templates_pass_clean`
- T-0087 → `tests/test_ds_monitor.py::test_monitor_shifted_distribution_is_alert`
- T-0133 → `tests/test_agent_goal.py::test_stop_condition_signature_stays_agent_shaped_until_dec`

## テスト（先に書いた・期待値は入力の構成から導く）
- `test_verified_by_file_only_is_error`：ファイル名だけの参照は error。
- `test_verified_by_unrelated_real_file_is_error`：実在する無関係ファイルを :: 無しで指しても error。
- `test_verified_by_comment_only_test_is_error`：コメント行だけのファイルで done が通らない（欠陥の再現封鎖）。
- `test_verified_by_string_literal_named_test_is_error`：文字列に名前が現れるだけでは実在とみなさない。
- `test_verified_by_class_method_form_is_ok` / `_missing_is_error`：クラス内メソッドの nodeid に対応する。
- `test_verified_by_parametrized_id_matches_base_name`：`[..]` を落として素の名前で照合する。
- 既存の `test_verified_by_missing_named_test_is_error` / `_present_named_test_is_ok` は緑のまま。

## ミューテーション実測（guard を壊すと RED）
- `_verified_by_problems` の「`::` 必須」分岐を外す → `test_verified_by_file_only_is_error` が RED。
- 実在照合を ast から本文 `in` に戻す → `test_verified_by_comment_only_test_is_error` が RED
  （コメント行だけのファイルで done が通ってしまう）。
