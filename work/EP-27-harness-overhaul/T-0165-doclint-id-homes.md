---
id: T-0165
kind: task
status: done
title: doclint の Windows 対応バグを直し、ID 接頭辞（ISS/REQ/DEC）の置き場実在検査を一般化する
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_doclint.py::test_known_commands_derived_from_venv_scripts_on_windows
  - tests/test_doclint.py::test_known_commands_still_derived_from_venv_bin_on_posix
  - tests/test_doclint.py::test_reference_to_prefix_whose_home_dir_is_absent_is_error
  - tests/test_doclint.py::test_bare_path_with_missing_home_dir_is_error
  - tests/test_doclint.py::test_python_string_literal_with_dead_id_reference_is_error
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0165 doclint の Windows 対応バグ修正＋ID 接頭辞の置き場実在検査の一般化

## 背景
1. `doclint._known_commands` が `.venv/bin` しか見ておらず、Windows（`.venv/Scripts`・拡張子付き実行
   ファイル）では `uv run marimo` 等が常に「既知のコマンドに無い」と info 報告されていた。
2. ID 参照の実在検査が `ISS-\d+` 専用で、EP-26 で `docs/decisions/` を撤去した後も `DEC-` 参照が
   （TOML/YAML のコメント・python の docstring/エラーメッセージ・スキル文書に）8 箇所残っていても
   機械的に検出できなかった。「置き場ディレクトリ自体が撤去された接頭辞への参照はすべて error」という
   一般化した検査が無かったのが原因。
3. 拡張子もスラッシュも持たない参照（`docs/decisions/DEC-0006` の形）は「判定に迷う参照」として
   これまで素通りしていた。

## やったこと
- `_known_commands`：`.venv/bin` と `.venv/Scripts` の両方を走査し、`p.stem`（拡張子を除いた名前）で
  登録するよう修正。
- `_ID_HOMES`（ISS→issues/・REQ→docs/requirements/・DEC→docs/decisions/）という接頭辞→置き場の登録簿を
  導入し、置き場ディレクトリ自体が存在しない接頭辞への参照はすべて error にした（ISS は
  `.harness/config.toml` の `issues.backend` で決まるので実行時に解決＝github: backend では検査しない、
  という既存仕様は維持）。
- 拡張子なし・スラッシュ終端なしの参照は、先頭 2 セグメントがディレクトリとして実在するかで判定する
  検査を追加。
- 走査対象に `src/**/*.py` の文字列リテラル（`ast` で抽出。コメントは対象外）を追加し、ID 参照の実在
  だけを見る（パス参照の検査は対象文書のみに留める＝ソースコードは識別子・正規表現の断片を含み、
  パスらしき文字列が地の文にも頻出するため過検出の的になる）。
- 上記の検査を追加すると、実際に本文へ残っていた `DEC-` 残骸のうち `src/harness/doclint.py` 自身の
  説明文中の例示（`DEC-0006`）と `src/harness/conventions.py` のエラーメッセージ例示（`ISS-1234`）、
  `.claude/skills/review/SKILL.md` の地の文（`docs/文書タスク...` が偶然パスらしく見えた誤検出）が
  新たに error として検出された。前者 2 件はプレースホルダ表記（`DEC-xxxx`・`ISS-xxxx`）へ直した
  （実在する課題 ID を例示に使わない）。後者は検査の欠陥だったので、抽出規則の側を直した
  （拡張子もスラッシュ終端も無い参照は、全セグメントが ASCII のパス構成文字のときだけ検査する）。
  正しい文章を検査に合わせて書き換えるのは、テストを書き換えて成功させるのと同じなので行わない。
- `pyproject.toml`（2 か所）・`.pre-commit-config.yaml`（1 か所）・`.github/workflows/ci.yaml`（2 か所）・
  `src/harness/doc_source_lint.py`（docstring・エラーメッセージ）・`.claude/skills/harvest/SKILL.md`・
  `templates/schedule/README.md`・`.harness/templates/requirement.md` に残っていた `DEC-` 短縮参照を、
  必要な語（本文の説明・正本の所在）を残したまま除去した。`work/`・`issues/` 配下の `DEC-` 参照は歴史の
  記録なので対象外。

## 受け入れ基準
- `uv run verify` 全成功。
- 一時プロジェクトで Windows venv（`.venv/Scripts/*.exe`）の実行ファイルが既知コマンドとして登録される
  ことをテストで固定（`test_known_commands_derived_from_venv_scripts_on_windows`）。
- 置き場ディレクトリが存在しない接頭辞への参照が error になることをテストで固定
  （`test_reference_to_prefix_whose_home_dir_is_absent_is_error`）。
- 現リポの正本ドキュメント・`src/**/*.py` に `DEC-` の死にリンクが残っていない
  （`test_real_repo_docs_have_no_dead_links`）。
