---
id: T-0191
kind: task
status: done
title: テストがこのリポジトリの実状態を仮定しないようにする
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_profiles.py::test_load_profiles_wires_declared_profile
  - tests/test_ops_profile.py::test_load_profiles_includes_ops
---
# T-0191 テストがこのリポジトリの実状態を仮定しない

## 何が問題だったか
`tests/test_profiles.py` と `tests/test_ops_profile.py` が「この config の `profiles` は
`[ds, serve, agent, ops]`」とテンプレート自身の設定値をハードコードしていた。`.harness/config.toml` を
`profiles = []` にした複製（非 DS 案件の正規手順）では、この 2 テストが実状態と食い違って落ちる。

実測（`profiles = []` の複製・`uv sync --all-extras`）：
- `tests/test_profiles.py::test_load_profiles_returns_ds_profile_for_this_repo` が unit 段階で FAILED。
- `tests/test_ops_profile.py::test_load_profiles_includes_ops` が integration 段階で FAILED。

他のテスト（`test_ci_lint`・`test_verification_mechanism` 等）は tmp_path 上に config を組み立てる形で
書かれている。そちらが正しい書き方。

## 直したこと
- 2 テストを tmp_path 上の config（または有効集合の明示引数）で書き直した。期待値は「宣言した profiles」
  から導出する（このリポの config 値は見ない）。
- `AGENTS.md` のテストの決まりごとに 1 行足した：
  **テストはこのリポジトリの実状態（`.harness/config.toml` の値・`issues/` の実在 ID・`work/` の中身）を
  仮定しない。** ソースの実在（`src/harness/<profile>/`）や生成物の構造の検査は可（可変領域でない）。

## 確かめ方
- 書き直した 2 テストが tmp 構成から緑（verified_by）。
- `profiles = []` の複製で、この 2 テストがもう落ちない（複製シミュレーションの実測は T-0192 の受け入れに含む）。
- 現リポ（全プロファイル有効）の `uv run verify` は従来どおり全成功。
