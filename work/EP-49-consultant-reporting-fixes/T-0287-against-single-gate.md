---
id: T-0287
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [T-0286]
verified_by:
  - tests/test_deliver_report.py::test_report_against_refuses_cleanly_when_the_overlay_is_broken
  - tests/test_deliver_report.py::test_report_against_refuses_cleanly_when_the_baseline_tree_is_broken
  - tests/test_deliver_formats.py::test_export_against_refuses_cleanly_when_the_baseline_tree_is_broken
---
# T-0287 `--against` 経路を `_prepare` の関門に畳む（D2）
設計は EP-49 の DESIGN.md（D2 節）。`report --against` は `_prepare` を先に通し、`changes_since`／
`export --against` の `baseline_map` の呼び出しは `BaselineError` だけでなく `ValueError`／`OSError` も
`_fail` に畳む。壊れた `docs/wbs.yaml` で `--against` を渡しても、素の traceback でなく「WBS を組み立てられない」
系の綺麗な拒否（exit 1・出力なし）になる。

## 受け入れ基準
- [ ] 壊れた overlay で `report --against` が未処理例外でなく exit 1・出力なしで拒否される。
- [ ] 壊れた overlay で `export --against`（baseline 側）も同様に綺麗に拒否される。
- [ ] 正常時の `--against` の挙動（前回からの変化・重ね描き）は変わらない。
