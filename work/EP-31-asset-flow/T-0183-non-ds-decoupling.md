---
id: T-0183
kind: task
status: done
title: 非 DS 案件で ds プロファイルを外せるようにする（テストの収集・mypy 対象・テンプレート複製）
created: 2026-07-10
depends_on: [T-0192]
verified_by:
  - tests/test_verification_mechanism.py::test_mypy_excludes_disabled_profile_source_and_tests
  - tests/test_verification_mechanism.py::test_mypy_excludes_empty_when_all_profiles_enabled
  - tests/test_verification_mechanism.py::test_glob_to_path_regex_matches_tests_dir_files
---
# T-0183 プロファイルを本当に外せるようにする

## 状態：T-0191＋T-0192 に統合して完了（この 3 点はすべて実装済み）
この既存タスクの 3 つの直し方は、EP-31 で分割した T-0191・T-0192 が丸ごと実現した。**別立てで残さず統合**した
理由：3 点は同じ根（「プロファイルを足せるが外せない」）で、テストの収集・型検査・CI 条文を一体で直さないと
`profiles = []` の複製が緑にならない（片方だけでは収集は通っても mypy が落ちる、の逆も然り）。分けると
受け入れ（複製が緑）が宙に浮く。この `verified_by` は 3 点のうち本タスク固有の**mypy 対象の profile 連動**を
指す（収集除外・ci_lint 条文の verified_by は T-0192 にある）。

- テストの収集（`collect_ignore` を profiles 連動に）→ **T-0192** が実装。命名規約は採らず（`work/` の
  `verified_by` を壊さない・弱い検査になる、の 2 点で不採用。理由は T-0192）。
- mypy の対象を profile 連動に → **本タスク**（`checks.py` の `_mypy_exclude_args`）。無効なプロファイルの
  `src/harness/<name>/` と所有テストを `--exclude` で外す。`checks.toml` は `["mypy"]` のまま・除外は実行時に
  profiles から導く（有効なプロファイルの列挙と同じ入口＝2 つ目の仕組みを作らない）。
- `ci_lint` の `--all-extras` 要求を「有効なプロファイルがある案件だけ」に → **T-0192** が実装（L-016 の
  依存監査は別ジョブで全部入りのまま）。

## 元の記述（参考）

## 何が問題か
`.harness/config.toml` の `profiles` からプロファイルを外しても、この雛形を複製した非 DS 案件は
`uv run verify` を通せない。

- `tests/` の 37 ファイルが `polars` / `sklearn` をトップレベルで import する。`conftest.py` に
  プロファイル連動の `collect_ignore` が無いので、収集の時点で ImportError になる。
- mypy の対象も `src/harness/**` 全体で、ds を入れない環境では型検査が通らない。
- `ci_lint.py`（175 行付近）は CI に `uv sync --all-extras` を要求する。DS の optional 依存
  （lightgbm 等）のテストを skip しないための規約だが、非 DS 案件には過剰。

つまり「プロファイル」は**足す**ことはできても**外す**ことができない。2 層モデル（中核とプロファイル）が
実際には成立していない。

## 直し方
- `tests/conftest.py` が `.harness/config.toml` の `profiles` を読み、載っていないプロファイルの
  テストを `collect_ignore_glob` で収集対象から外す。テストのファイル名からプロファイルが決まるように
  命名規約を明文化する（`test_ds_*.py`・`test_agent_*.py`・`test_serve_*.py`・`test_ops_*.py`）。
  規約から外れた名前は検査で失敗にする（`conventions.run_checks` に足す）。
- mypy の対象をプロファイルに連動させる（`checks.toml` 側で決める）。
- `ci_lint` の `--all-extras` 要求を「有効なプロファイルの extra をすべて入れること」に読み替える。

## 確かめ方（これが本体）
一時ディレクトリに `profiles = []` の複製を作り、`uv run verify` が緑になることを **e2e で確かめる**。
これができない限り「非 DS 案件で使える」と言ってはいけない。逆にこのテストが 1 本あれば、以後
プロファイルの結線が壊れたら必ず落ちる。

## 受け入れ基準
- `profiles = []` の複製で `uv run verify` が緑（e2e テスト 1 本）。
- `profiles = ["harness.ds"]` の複製では ds のテストが収集される（同じ e2e で対の確認）。
- 命名規約から外れたテストファイルが検査で失敗する。
- 現リポ（全プロファイル有効）の `uv run verify` は従来どおり全成功。
