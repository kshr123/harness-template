---
id: T-0306
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
  - tests/test_code_doc_lint.py::test_substring_of_sibling_does_not_mask_module
  - tests/test_conventions.py::test_np_random_seed_call_is_error_with_file_and_line
  - tests/test_lintkit.py::test_rule_from_callable_preserves_behavior_and_derives_name_summary
---
# T-0306 P4：lintkit の前向き部品を実稼働にする（ISS-0020 の決着＝使う）

ISS-0020（未使用の前向き部品は使うか撤回するか）を「使う」で決着：

- **word_bounded**（P4a）：code_doc_lint の語境界（`_NAME_BOUNDARY`/`_NAME_END`/`_mentioned`）を `ids.word_bounded` へ
  （byte 一致＝旧テスト無改変で緑）。
- **Rule / run**（P4c）：checks.py の runner を `lintkit.run(rules, root)` へ。既存の検査は `Rule.from_callable` で包み、
  Corpus を 1 度だけ作って全ルールへ渡す（挙動不変）。
- **Corpus**（P4b）：`conventions` を Corpus ネイティブな `Rule`（`_scan(corpus)`＝`corpus.rel`/`corpus.parse` を使う）に。
  `run_checks(root)` はテスト用の薄い包み。core.md 表の行名は従来どおり（`rule.name="conventions.run_checks"`）＝再生成不要。
  doc_sync は Rule も読めるように（`rule.name`/`rule.summary`）。
- **Exemptions クラス**：唯一 consumer が付かなかったので**撤回**（`validate_exemptions` は 4 lint が使うので残す）。

これで lintkit に死蔵コードは無い（ids・validate_exemptions・Corpus・Rule・run はすべて実運用）。P5（workflows 抽出）・
P6（agent lint→バリデータ）は ISS-0020 の名指し部品には関わらない別の統合＝EP-54 の任意フェーズとして継続。
