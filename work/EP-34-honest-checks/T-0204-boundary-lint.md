---
id: T-0204
kind: task
status: done
title: boundary_lint 中核がプロファイルを import しないことを ast で検査する
requirements: [REQ-001]
created: 2026-07-11
depends_on: []
verified_by:
  - tests/test_boundary_lint.py::test_core_absolute_import_of_profile_is_error
  - tests/test_boundary_lint.py::test_core_from_import_of_profile_is_error
  - tests/test_boundary_lint.py::test_core_relative_import_of_profile_is_error
  - tests/test_boundary_lint.py::test_core_lazy_import_inside_function_is_error_and_marked
  - tests/test_boundary_lint.py::test_core_importing_core_is_ok
  - tests/test_boundary_lint.py::test_profile_to_profile_import_is_out_of_scope
  - tests/test_boundary_lint.py::test_profile_name_in_string_is_not_flagged
  - tests/test_boundary_lint.py::test_blank_exempt_reason_raises
  - tests/test_boundary_lint.py::test_real_repo_core_does_not_import_profiles
---
# T-0204 boundary_lint（中核がプロファイルを import しない）

## 狙い
`docs/core.md` は「中核（`src/harness/*.py`）はプロファイル（ds・serve・agent・ops）のコードを import
しない」を最重要の不変量として宣言していたが、担保は規約 (c)（人が気をつける）だけだった。**import 文と
いう構文の印**があり、対象集合（`src/harness/*.py`）はファイルシステムから機械的に導けるので (b)（機械が
検出する）にできる。

## 直したこと
`src/harness/boundary_lint.py` を新設した（coverage_lint / code_doc_lint と同じ ast・allowlist の作法）：
- 対象＝`src/harness/*.py`（直下・非再帰の中核モジュール）。各ファイルを **ast** で解析し
  （文字列 grep ではない＝コメント・docstring 内の "import harness.ds" に誤爆しない）、
  `harness.(ds|serve|agent|ops)` への import を error にする。
- `ast.walk` で全ノードを見るので、**関数内の遅延 import も検出**する（メッセージに「遅延 import」と印を
  付ける。トップレベルの import だけを見る抜け道を塞ぐ）。
- 相対 import（`from . import ds`・`from .ds.models import X`）も親パッケージ `harness` を起点に解決する。
- 免除は `_EXEMPT`（(中核モジュール名, import 先モジュール) → 理由）だけ。理由必須（空は ValueError）。

## 配線
`PM_CHECKS` は `src/harness/checks.py` にあるが、当タスクの実施時点で checks.py は別エージェントが並行編集中の
ため直接触れない指示だった。そこで `pm.lint`（既に `PM_CHECKS` の一員）の末尾から `boundary_lint.run_checks`
を呼び、verify に載せた（循環 import を避けるため `pm.lint` 内で遅延 import する）。効果は同じ（verify で
落ちる）で、`docs/core.md` のモジュール一覧に `boundary_lint.py` を明記した。checks.py が空くのを待って
`PM_CHECKS` へ独立エントリとして移す方が表示上は素直（後続の整理課題）。

## 発見した既存の越境（直さずに報告）
中核 → プロファイルの越境は **0 件**（`test_real_repo_core_does_not_import_profiles` が緑）。
一方、**プロファイル同士**の遅延 import が 5 件ある（この検査の対象外＝別の境界の話。直していない）：
- `src/harness/agent/cli.py:422` → `harness.ds.experiment`（遅延）
- `src/harness/serve/app.py:27` → `harness.ds.models`（遅延）
- `src/harness/serve/runtime.py:27` → `harness.ds.models`（遅延）
- `src/harness/serve/runtime.py:47` → `harness.ds`（遅延）
- `src/harness/serve/runtime.py:81` → `harness.ds`（遅延）

## テスト（先に書いた・期待値は入力の構成から導く）
- 絶対 import・from import・相対 import の越境がそれぞれ error。
- 遅延 import が error で、メッセージに「遅延 import」と付く。
- 中核が中核（`harness.pm`）を import するのは OK・stdlib も OK。
- プロファイル配下（`src/harness/ds/…`）の越境は対象外＝error にしない。
- 文字列・コメント中の "import harness.ds" は当たらない（grep との違い）。
- 免除の理由が空は ValueError（fail closed）。
- `test_real_repo_core_does_not_import_profiles`：現リポの中核は越境 0 件（回帰）。

## ミューテーション実測（guard を壊すと RED）
- `_violations` で `ast.walk` を `tree.body` 走査に狭める（＝遅延 import を見逃す）→
  `test_core_lazy_import_inside_function_is_error_and_marked` が RED。
- `_profile_of` の判定を握りつぶす（常に None）→ 越境検出の全テストが RED。
