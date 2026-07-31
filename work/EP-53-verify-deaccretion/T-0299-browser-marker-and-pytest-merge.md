---
id: T-0299
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
  - tests/test_verification_mechanism.py::test_merge_pytest_collapses_layers_into_one_union
  - tests/test_verification_mechanism.py::test_merge_pytest_leaves_single_or_nonstandard_pytest_untouched
  - tests/test_verification_mechanism.py::test_checks_toml_uses_only_registered_markers
  - tests/test_ci_config.py::test_ci_runs_browser_tests_since_verify_excludes_them
---
# T-0299 描画テストを verify から外す（browser マーカー）＋ full の pytest を 1 回に統合

「毎回 Chrome が起動するのは違和感」への対処。fable の棚卸しで確定：描画の**幾何（座標）は Python 計算で
`test_deliver_geometry`（unit）が毎回ブラウザ無しで検証済み**＝Chrome が要るのは JS/DOM の振る舞い
（依存ハイライト・折りたたみ）の 3 本だけ。

- `browser` マーカーを新設（pyproject）。`tests/test_deliver_browser.py` を `[integration, browser]` に。
- `checks.toml` の standard を `integration and not slow and not browser`＝**既定の verify で Chrome を起動しない**。
- 描画を触るタスクでは `check --scope diff` が deliver 変更として browser テストを回す（そのときだけ Chrome）。
- merge 前に **CI（verify ジョブ）が `pytest -m browser` を必須実行**＝どこにも走らない黙った空白を作らない。
- full で pytest が 3 回（fast+standard+full の累積）走るのを、式の論理和で **1 回に統合**（`_merge_pytest`）＝
  走るテスト集合は完全一致（門番が黙って減らない）・約 5〜8 秒短縮。
