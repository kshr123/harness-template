---
id: T-0181
kind: task
status: done
title: doc_source_lint の走査対象を広げ ISS 参照も error にする
created: 2026-07-10
depends_on: [T-0190]
verified_by:
  - tests/test_doc_source_lint.py::test_source_dirs_prose_is_scanned
  - tests/test_doc_source_lint.py::test_durable_doc_referencing_issue_is_error
  - tests/test_doc_source_lint.py::test_python_data_strings_are_not_flagged
  - tests/test_doc_source_lint.py::test_mutable_areas_are_not_scanned
---
# T-0181 doc_source_lint の適用範囲を広げる

## 何を変えたか
既存の封鎖（恒久ドキュメント → `work/` 参照を禁じる）の**穴埋め**。参照の向き（複製後も残る資産 → 消える
一時単位）そのものを塞ぐ。残骸を grep する新しい lint は作らない（L-017）。

- **走査対象を拡大**：`README.md`・`AGENTS.md`・`docs/*.md` に加え、`src/harness/**`・`tests/**`・
  `templates/**`・`.claude/skills/**`（＝複製後も残る資産）。`issues/` 自身・`work/` 自身は走査しない
  （一時単位どうしの相互参照は正当）。
- **`ISS-…` も `work/…` と同じく error**。`ISS-<番号>`（角括弧）・`ISS-0000`/`ISS-XXXX`（型録表記）は
  具体単位を指さないので拾わない。
- **`.py` はコメント＋docstring（人向けの散文）だけを走査**。文字列リテラル（関数引数・アサーション）は
  対象外＝テストが合成の一時ツリーを組む入力 `"work/EP-01/…"`・`"ISS-9999"` を**データ**として渡すのは正当。
  コメントはコメント本文だけを見る（`assert "…ISS-…"  # 説明` の行で、データ側の ID を拾わないため）。
- 免除は `_EXEMPT`（リポジトリ相対パス → 理由。空は `ValueError`）。`docs/template-copy.md` は既存どおり免除。

## 同じタスクで直した赤
走査を広げると `templates/experiment/train.py` の `work/EP-06-…`・`work/E-0001`（docstring・コメント）が赤に
なるので、由来の文言を削り本文の説明に直した（由来は git が持つ）。さらに tests/ の散文（docstring・コメント）に
残っていた `ISS-…`・`work/…` の設計根拠参照（13 箇所）も同じ原則で剥がした（`conftest.py` は ISS 参照コメントの
行のみ・収集の仕組みには触れていない）。

## 検証
`uv run verify` 全成功。ミューテーション：`src/harness/checks.py` の `PM_CHECKS` から `doc_source_lint` を外すと
`test_doc_source_lint_is_wired_into_pm_checks` が RED、`_ISS_REF_RE` を無効化すると
`test_durable_doc_referencing_issue_is_error` が RED になることを実測（戻した）。
