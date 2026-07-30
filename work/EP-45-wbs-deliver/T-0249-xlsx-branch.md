---
id: T-0249
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 2
requirements: [REQ-006]
depends_on: [T-0248]
verified_by:
  - tests/test_deliver_formats.py::test_the_default_format_is_html_and_the_suffix_follows_it
  - tests/test_deliver_formats.py::test_the_spreadsheet_branch_appears_only_with_its_dependency
  - tests/test_deliver_formats.py::test_every_registered_format_explains_itself
  - tests/test_deliver_formats.py::test_an_unknown_format_fails_with_the_candidates
  - tests/test_deliver_formats.py::test_the_spreadsheet_matches_the_tree
  - tests/test_deliver_formats.py::test_the_spreadsheet_says_it_is_a_copy
  - tests/test_deliver_formats.py::test_the_spreadsheet_folds_by_depth
---
# T-0249 先方の様式指定に応える出力形式の枝

既定の成果物は HTML 1 つのまま（同格の成果物が 2 つ並ぶ状態を作らない）。日本の受託では先方の管理部門が
「WBS は表計算で」と様式を指定してくることが実際にあり、HTML しか出せないと最初の 1 案件で折れる。

## 作ったもの

- 出力形式の登録簿 `formats.py`（`RENDERERS`）。既存のモデル保存形式・モデル種と同じ条件登録にした
  ＝**その依存が入っている案件でだけ形式が生える**。入れなければ一覧にも出ないので、選べる形式＝使える形式。
- 表計算の写し `xlsx.py`（階層は表計算側の折りたたみ、週ごとの塗りでガント、日付は日付として書く）。
- `uv run wbs formats`（出せる形式の一覧）と `uv run wbs export --format <形式>`。
- optional 依存 `openpyxl`（ライブラリ名＝extra 名の既存の作法）。型スタブは別配布なので `types-openpyxl`
  を dev に入れた（スタブがある以上、mypy の「スタブが無いライブラリ」一覧には混ぜない）。

## 取り込みを作らなかった理由

表計算は編集を誘う道具なので、返送されたファイルを読む口を開けると、行の挿入・並べ替え・書式でセルの
対応が黙って壊れる（＝二重台帳への入口）。読み取り専用の写しであることをシートの先頭に明記して渡し、
クライアントの変更の要望は要求層で受ける。

## 受け入れ基準

- [x] 依存が入っていない環境で、出力形式の一覧にその形式が出ないか（入れれば出るか）。
- [x] 出した表を読み戻したとき、行の構成・日付・日数が木から導いた値と一致するか。
- [x] 既定の出力（形式を指定しない呼び出し）が HTML 1 つのままか（表計算が勝手に並ばないか）。
- [x] 知らない形式を指定したとき、候補を添えて失敗するか。
- [x] 写しであることが表そのものに書いてあるか。
