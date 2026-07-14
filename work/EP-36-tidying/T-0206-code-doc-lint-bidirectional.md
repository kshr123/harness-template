---
id: T-0206
kind: task
status: done
title: code_doc_lint を双方向にして役割一覧の残骸を止める（ISS-0015 を閉じる・当初の doc_sync 統合案は見直し）
created: 2026-07-14
closed: 2026-07-14
depends_on: []
verified_by:
  - tests/test_code_doc_lint.py::test_reverse_stale_table_row_is_error
  - tests/test_code_doc_lint.py::test_reverse_stale_bullet_row_is_error
  - tests/test_code_doc_lint.py::test_reverse_ignores_prose_mentions
  - tests/test_code_doc_lint.py::test_reverse_full_path_backtick_is_an_escape_hatch
  - tests/test_code_doc_lint.py::test_reverse_scoped_to_the_docs_own_directory
  - tests/test_code_doc_lint.py::test_declared_modules_extractor_is_not_silently_empty
  - tests/test_code_doc_lint.py::test_role_lists_in_code_docs_stay_extractable
  - tests/test_code_doc_lint.py::test_real_repo_has_no_stale_role_rows
---
## 当初案を見直した（進め方の進化）
一覧の見出しでは「`code_doc_lint` を `doc_sync` の生成へ統合する（検査 1 本・免除リスト 1 個・ISS-0015 が
同時に消える）」だった。だが実物の役割一覧を読むと、これは採れない：`docs/core.md` の「モジュール一覧」も
プロファイルの `*-code.md` の箇条書きも、**編集された散文**（相互参照・使うプロファイル別のグループ分け・
例示・「〜とは別物」の注記）で、docstring 1 行目から機械生成するとこの役割ドキュメント（T-0155 で作った価値）を
薄くする。手段（検査を 1 本に畳む）を追って目的（人が役割を辿れる）を損なう典型なので、生成案は捨てた。

残った本当の価値は ISS-0015（消したモジュールの説明の行が残るのを止める）。これは生成でなく**逆向きの照合**で
閉じられる。免除リストは順向きに要るので残す（＝「免除リスト 1 個消す」も生成案の前提だった）。

## 実装（done）
- `src/harness/code_doc_lint.py` を双方向に：
  - 逆向き `_reverse_checks`：役割一覧の行の**先頭**に来る `<名>.py` を対応する置き場に照合する。抽出は
    `_ROLE_ROW_RE`（行頭が表区切り `|` か箇条書き `-`/`*`、直後のバッククォート名）で、散文の途中の言及や
    フルパス表記（`/` を含むので不一致）は拾わない（ISS-0015 が挙げた誤検出をこの絞りで避ける）。
  - 置き場は doc の名前で決める：`core` → `src/harness`・プロファイル → `src/harness/<名>`（同名の別モジュール
    `models.py` を取り違えない）。
  - docstring を「双方向」に更新し、旧「未解決の既知の穴」の段落を消した。
- `docs/core.md` の `code_doc_lint.py` の役割の行を双方向の説明に更新（この行自身も逆向きの照合対象＝
  自己言及で自分の実在も確かめる）。
- `issues/ISS-0015` を `state: resolved`・`promoted_to: T-0206` に。

## 受け入れ基準（満たした）
- 表の行・箇条書きの残骸を error にする（`test_reverse_stale_table_row_is_error`・`..._bullet_row_is_error`）。
- 散文の言及・フルパス表記では誤検出しない（`..._ignores_prose_mentions`・`..._full_path_backtick_is_an_escape_hatch`）。
- 置き場は doc の名前で絞る（`..._scoped_to_the_docs_own_directory`）。
- 抽出器の黙った破損を防ぐ（`..._extractor_is_not_silently_empty`：実データで非空＋中核の一覧と一致を固定）。
- 現リポに残骸ゼロの回帰（`test_real_repo_has_no_stale_role_rows`）。

# T-0206 code_doc_lint の逆向き（ISS-0015）

役割一覧が挙げるモジュールが実在するかを検査する。消したモジュールの説明の行が残り、読者が存在しない
コードを探すのを止める。
