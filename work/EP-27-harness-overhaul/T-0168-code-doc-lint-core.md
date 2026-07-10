---
id: T-0168
kind: task
status: done
title: code_doc_lint を中核モジュールにも効かせ、docs/core.md に役割一覧を置く
created: 2026-07-10
depends_on: [T-0167]
verified_by:
  - tests/test_code_doc_lint.py::test_undocumented_core_module_is_error
  - tests/test_code_doc_lint.py::test_core_init_and_private_modules_are_ignored
  - tests/test_code_doc_lint.py::test_core_cli_is_scanned
  - tests/test_code_doc_lint.py::test_non_profile_subdirectories_are_not_scanned
  - tests/test_code_doc_lint.py::test_profile_module_is_not_reported_against_the_core_doc
  - tests/test_code_doc_lint.py::test_core_exempt_key_suppresses_error
  - tests/test_code_doc_lint.py::test_path_mention_of_a_different_module_does_not_count
  - tests/test_code_doc_lint.py::test_full_path_mention_of_the_module_itself_counts
  - tests/test_code_doc_lint.py::test_relative_path_mention_of_the_module_itself_counts
  - tests/test_code_doc_lint.py::test_real_repo_core_modules_are_all_scanned
  - tests/test_code_doc_lint.py::test_real_repo_profile_modules_are_documented
---
# T-0168 中核モジュールの触れ忘れ検出

## 背景
`code_doc_lint` は「プロファイル（`profile.py` を持つディレクトリ）の公開モジュールが、そのプロファイルの
正本ドキュメントに載っているか」を検査する。docstring に **「core 直下（プロファイルでない共通部品）は対象外」**
と明記されており、`src/harness/*.py` の 18 モジュールには「新しく足したのに誰も説明を書かない」を止める
仕組みが無かった。理由は「core の正本ドキュメントが存在しないから」で、T-0167 で `docs/core.md` を作ったので
その理由は消えた。

## やること
- `code_doc_lint` の対象に `src/harness/*.py`（非再帰）を追加する。除外は `__init__.py` と `_` 始まりだけ。
  `cli.py` は含める（プロファイル側でも `cli.py` を除外していないので対称）。`profile.py` は core に無い。
- 参照先の正本は `docs/core.md`（＋あれば `docs/core-code.md`）。プロファイルと同じ「連結して探す」方式。
- 免除の鍵は `core/<モジュール>.py`（既存の `<プロファイル>/<モジュール>.py` と同じ形。`src/harness/core/` という
  ディレクトリは無いので衝突しない）。理由必須は据え置き。
- `docs/core.md` に中核モジュールの役割一覧（マーカーの外・手書きの表）を置く。3 つに分けて書く：
  1. **中核のしくみ**（作業単位・課題・設定・プロファイル読み込み・検証の入口・CLI）
  2. **検査**（`docs/core.md` の自動生成表と対応する）
  3. **プロファイルが共有する部品**（`registry.py`・`storage.py`・`fingerprint.py`）と**テストの土台**（`testing.py`）
     — これらは中核の検査系からは一度も import されていない。「複数プロファイルで再利用するので中核に置いた」
     ものであり、中核のしくみ自身が使う `models.py`（`pm`・`issues` が使う型）とは性格が違う。

## 既存テストの上書き
`tests/test_code_doc_lint.py::test_non_profile_dirs_are_not_scanned` は「core 直下の `lonely.py` は対象外」を
受け入れ基準として表明している。本タスクはその仕様を意図的に反転させるので、テストを削除せず書き換え、
「プロファイルでない**下位ディレクトリ**（`util/`）は依然として対象外／core **直下**は対象になった」を
固定し直す（`src/harness/*.py` は非再帰の glob）。

## 実測（検査が実際に失敗させることの確認）
- 対象を広げた直後、中核 18 モジュールのうち **16 件**が未記載として error になった（`checks.py` と
  `doc_sync.py` だけは T-0167 の散文で既に触れられていた）。役割一覧を書いて 0 件に。
- 役割表から `storage.py` の行を消す → `src/harness/storage.py` が error。
- `_core_modules` が常に空を返すよう壊す → 4 本のテストが失敗（うち 1 本は「空集合を『全部載っている』と
  読み違えない」ための件数の検査）。glob の書き間違いで検査が黙って無効化されるのを防ぐ。

## 独立レビューの指摘と対応（判定：条件付き可 → 重大 1 件を修正）
**重大（R-1）：`_mentioned` の語境界が `/` を通す。** 直前が `_`・英数のときだけ弾いていたので、
`docs/core.md` が中核の `models.py` に一切触れず **`src/harness/ds/models.py`（別モジュール）へのパス**だけを
含んでいても「載っている」と判定されていた。逆向きも同じ。今日は実害が無いが、その段落を書き換えた瞬間に
守りが黙って消える。実測で再現（`_mentioned('models.py', 'src/harness/ds/models.py') == True`）。

修正：数える形を 2 つに限定した。(1) 素の名前が独立した語として現れる（直前に `/`・`.`・`-` も許さない）、
(2) **自分自身の置き場**を指すパス（`src/harness/models.py`・`harness/models.py`）が現れる。他モジュールへの
パスに名前が含まれているだけの一致は数えない。テストを先に書いて失敗を確認してから直した。
検査を厳しくしても現リポの `docs/core.md` は 18 行すべて素の名前で書いてあるので、文章を歪めずに通る。

その他：
- `__init__.py` の明示除外は `_` 始まりに含まれる**死んだ条件**だった（ミューテーションが生存する＝等価変異）。
  除去し、理由を docstring に書いた（`_normalize` と同じ轍）。
- 免除の鍵を `core/<名>.py` からリポジトリ相対のパスに変更。短縮鍵は将来 `src/harness/core/` という
  プロファイルを作った瞬間に中核と衝突し、参照先ドキュメントも区別できなくなる。
- 逆向きの腐り（モジュールを消しても docs の行が残る）を ISS-0015 に起票。`docs/core.md` にも明記した。
- 用語：「モジュールの地図」→「モジュール一覧」。

## 受け入れ基準
- 一時プロジェクトで、`docs/core.md` に触れられていない core 直下のモジュール＝error。触れれば消える。
  `docs/core-code.md` 側でも可。
- `__init__.py`・`_` 始まりは対象外。`src/harness/<名前>/` の下（`profile.py` 無し）は対象外のまま。
- 免除の鍵 `core/<モジュール>.py` が効き、理由が空なら ValueError。
- 現リポの中核 18 モジュールがすべて `docs/core.md` に載っている（回帰テスト）。
- `uv run verify` 全成功（docstring を変えたので `uv run doc-sync` の再生成が要る）。
