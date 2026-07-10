---
id: T-0183
kind: task
status: todo
title: 非 DS 案件で ds プロファイルを外せるようにする（テストの収集とテンプレート複製）
created: 2026-07-10
depends_on: []
verified_by: []
---
# T-0183 プロファイルを本当に外せるようにする

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
