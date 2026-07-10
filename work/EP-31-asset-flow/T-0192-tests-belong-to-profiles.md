---
id: T-0192
kind: task
status: done
title: テストをプロファイルの持ち物にする（無効なプロファイルのテストは収集も型検査もしない）
created: 2026-07-10
depends_on: [T-0191]
verified_by:
  - tests/test_profiles.py::test_disabled_profiles_is_shipped_minus_enabled
  - tests/test_profiles.py::test_ds_profile_owns_its_optional_dependency_tests
  - tests/test_profiles.py::test_profile_test_globs_match_only_existing_files
  - tests/test_verification_mechanism.py::test_mypy_excludes_disabled_profile_source_and_tests
  - tests/test_verification_mechanism.py::test_mypy_excludes_empty_when_all_profiles_enabled
  - tests/test_ci_lint.py::test_missing_all_extras_not_flagged_for_core_only_project
  - tests/test_ci_lint.py::test_missing_all_extras_flagged
---
# T-0192 テストをプロファイルの持ち物にする

## 何が問題だったか
非 DS 案件（`profiles = []`）が素の `uv sync` で `uv run verify` を起動できない。実測（`profiles = []`）：

- 素の `uv sync`（extra なし）：pytest 収集で **45 errors**（`tests/` が polars・numpy・fastapi・anthropic を
  トップレベル import する）。加えて mypy(strict) が **136 errors**（`src/harness/{ds,serve,agent}` のソースと
  profile テストが型スタブの無い optional 依存を import する。うち約 130 は import-not-found、残りは fastapi が
  Any になったことによる untyped-decorator の連鎖）。
- `uv sync --all-extras`：収集は通るが、T-0191 で直した 2 テストが実状態を仮定して落ちる（→ T-0191）。

つまり「プロファイル」は**足す**ことはできても**外す**ことができていなかった。

## 採った設計：collect_ignore（プロファイル連動）。ディレクトリ分割・命名規約は採らない。
選択肢は「conftest の collect_ignore（プロファイル連動）」か「ディレクトリ分割（tests/ds/ 等）」だった。
独立レビューはディレクトリ分割を推した（「改名リストが短く lint も単純」）が、**実測で両方の物理移動が
使えないと分かった**ので collect_ignore を採った。理由：

1. **ファイル移動・改名は `work/` の `verified_by` を壊す。** done タスクの `verified_by` は約 500 箇所が
   具体的なテストパス（例 `tests/test_ds_pipeline.py::…` が 41 箇所）を指す。pm 検査は指す先の実在を要求するので、
   移動/改名すると `work/`（案件所有の可変領域）を数百箇所書き換える羽目になる。EP-31 の境界（本体は移動しても
   案件の `work/` を書き換えない）にも反する。ディレクトリ分割は `parents[1]`→`parents[2]` の修正も約 8 ファイルに
   波及する。**移動しないこと自体が要件**なので、位置でも名前でもなく**宣言**で所有を表す collect_ignore にした。
2. **命名規約は弱い検査になる**（AGENTS「(b) を名乗るには対象集合が構文・型・登録から導けること」）。
   未接頭辞の profile テスト（`test_cli_*`・`test_forecast` 等）を「実は ds のテスト」と機械が判定する術は無く、
   新しい未接頭辞テストの第 1 号を必ず見逃す。ディレクトリ分割の「位置＝所有」は強いが (1) で不採用。
3. **collect_ignore なら 2 つ目の台帳を作らずに済む。** 所有は `Profile.test_globs` に、`pm_checks` と**同じ束ね方**で
   宣言する（`profiles.py`）。conftest は無効なプロファイル（config に載っていない同梱プロファイル）の
   `test_globs` を `collect_ignore_glob` にする。glob は**複数プロファイルで共有**できる（例
   `test_serve_app.py` は ds と serve の両方が所有＝どちらかを外すと収集しない）＝多所有を自然に表せる。

## やったこと
- `Profile` に `test_globs` を足し、各 `profile.py`（ds/serve/agent/ops）が所有テストの glob を宣言。
- `profiles.discover_profiles(root)`（同梱プロファイルの発見）と `disabled_profiles(root, enabled=None)`
  （有効化されていない同梱プロファイル）を追加。プロファイルのモジュールは軽い（重い依存を top で import
  しない規約）ので、extra 未導入でも import して glob を読める。
- `tests/conftest.py`：`collect_ignore_glob = 無効なプロファイルの test_globs の和`。全プロファイル有効な
  当リポでは空＝全テストが従来どおり収集される。ファイルは 1 つも移動・改名していない。
- `src/harness/checks.py`：mypy 実行時に、無効なプロファイルの `src/harness/<name>/` と所有テスト glob を
  `--exclude` で外す（`checks.toml` は `["mypy"]` のまま・除外は profiles から実行時に導く）。有効化＝依存も
  入れる前提なので、有効なプロファイルだけを型検査する。当リポ（全有効）は除外なし＝従来どおり。
- `src/harness/ops/ci_lint.py`：`uv sync --all-extras` の要求を profile 従属にした。`profiles = []` の案件は
  optional 依存が無い＝素の `uv sync` でよい（`--all-extras` を強制しない）。**L-016（依存監査は全部入り）は
  壊さない**：pip-audit の監査ジョブは案件の `.github/workflows/ci.yaml` にあり ci_lint の対象外＝全部入りのまま。
  「テストを回す環境を profile に絞る」ことと「監査は全部入り」は別軸。AGENTS の条文も同じ趣旨に直した。

## 確かめ方（実測）
- 単体：`disabled_profiles`・`test_globs` の所有・mypy 除外の構築・ci_lint の profile 従属を、tmp 構成/明示引数から
  導ける期待値で確かめる（verified_by）。
- 複製シミュレーション（手動実測。自動化は T-0195）：clone → `profiles = []` → 素の `uv sync` → `uv run verify` が
  収集 0 error・mypy 緑・pytest 緑になる（`work/`・`issues/` を消したときの doclint デッドロックは T-0190 の担当なので
  残す）。
- ミューテーション：conftest の `collect_ignore_glob` を空に固定すると、素の環境で収集が 45 error に戻る（RED）。
- 現リポ（全プロファイル有効）の `uv run verify` は従来どおり全テストが走って全成功。
