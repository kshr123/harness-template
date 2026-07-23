---
id: T-0247
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 3
requirements: [REQ-009]
depends_on: [T-0245]
verified_by:
  - tests/test_deliver_editor.py::test_editing_a_date_changes_exactly_one_line
  - tests/test_deliver_editor.py::test_editing_a_manual_row_changes_exactly_one_line
  - tests/test_deliver_editor.py::test_a_stale_reader_cannot_overwrite
  - tests/test_deliver_editor.py::test_the_returned_digest_lets_the_next_save_through
  - tests/test_deliver_editor.py::test_bad_values_are_refused_and_nothing_is_written
  - tests/test_deliver_editor.py::test_fields_outside_the_allowed_set_are_refused
  - tests/test_deliver_editor.py::test_an_edit_that_breaks_the_invariants_is_rolled_back
  - tests/test_deliver_server.py::test_saving_without_the_token_is_refused
  - tests/test_deliver_server.py::test_a_request_naming_another_host_is_refused
  - tests/test_deliver_server.py::test_saving_from_a_stale_page_is_refused_with_a_reason
  - tests/test_deliver_server.py::test_saving_writes_to_the_source_and_returns_the_new_digest
  - tests/test_deliver_server.py::test_page_marks_the_editable_cells
---
# T-0247 ブラウザで編集して正本へ書き戻す面を作る

参照だけでなく編集もできるようにする。書き込み先は正本ひとつ（第 2 の台帳を作らない）。

## 作ったもの

- `uv run wbs edit` … 127.0.0.1 にローカルサーバを立て、表のセルをその場で直せる画面を出す
  （クリックで入力に変わり、Enter で保存・Esc で取り消し）。
- **閲覧と編集は同じ描き方**（`render.render_html` に `editable` を渡すだけ）。違うのは、直せる欄に
  書き戻し先の目印が付くことと、保存の口があることだけ。ファイルに書き出す生成物は常に保存の口を持たない
  ので、渡した先で編集はできない。
- 書き戻し（`editor.py`）は frontmatter・上書きファイルの**そのキーの行だけを置き換える**（設定ファイルの
  1 行だけを書き換える既存の作法と同じ）。ファイル全体を書き出し直さないので、コメント・並び・引用符が
  そのまま残り、差分は 1 か所あたり 1 行に収まる。引用符は必要なときだけ付ける（要らない引用符で差分を
  読みにくくしない）。
- 直せる欄は決め打ちの一覧だけ。**導出される値には編集の口が無い**ので、画面から矛盾を入力できない。
  親の行は表題だけ直せる（日程・状態は子から導くため直す先が無い）。
- 保存に成功したら画面を作り直す。日数・ロールアップ・進捗・遅れは導出値で 1 か所直すと他も動くため、
  画面側で計算をやり直すと計算が 2 か所になる。導出はサーバの 1 か所に置いたまま毎回まるごと描き直す。
- 安全のため 3 つ重ねる：読んだ時点の指紋の突き合わせ（読み取り〜書き込みを 1 つの錠で囲む・成功時は
  新しい指紋を返す）／書く前の型検査／書いた後の不変条件の検査（失敗したら元へ戻す）。
- 書き込みの口の守り（`server.py`）：起動ごとの合言葉を本文に埋めて独自ヘッダで送らせる（URL に載せない）・
  名乗ったホスト名の検査・待ち受けは 127.0.0.1 のみ・放置で自動終了。

## 受け入れ基準

- [x] 画面から日付を変えて保存すると、正本の該当行だけが書き換わるか（他の行・コメントが動かないか）。
- [x] 保存の前に正本が別の手で書き換わっていたとき、上書きせずに拒否するか。
- [x] 続けて 2 回保存できるか（1 回目の成功後に誤って拒否されないか）。
- [x] トークンの無い要求・別のホスト名を名乗る要求を拒否するか。
- [x] 検査に失敗する内容は保存されないか（書いた後の検査で落ちたら元へ戻るか）。

## 実プロセスでの確認

見本の案件で `uv run wbs edit` を起動し、合言葉なし＝403・別ホスト名＝400・矛盾する日付＝409（正本は
変わらず）・矛盾しない日付＝200 で 1 行だけ書き換わる・返った指紋で続けて 2 回目も 200・手動行の書き戻しも
200 を確認した。依存の順序の検査が実際に「後続の開始を追い越す変更」を止めた。

## 残した課題

担当者が複数の手動行（`assignees`）は画面から直せない（一覧の値なので行置換の形に載らない）。
必要になったらテキストで直す。
