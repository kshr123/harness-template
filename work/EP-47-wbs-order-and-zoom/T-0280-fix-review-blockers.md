---
id: T-0280
kind: task
status: done
created: 2026-07-30
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [T-0279]
verified_by:
  - tests/test_deliver_formats.py::test_the_spreadsheet_does_not_write_live_formulas_from_user_text
  - tests/test_deliver_render.py::test_user_text_is_html_escaped_everywhere
  - tests/test_deliver_lint.py::test_same_manual_row_in_two_sections_fails
  - tests/test_deliver_script.py::test_lane_click_computes_the_day_in_utc
---
# T-0280 独立コードレビュー（fable×4）で出たブロッカー3件を直し、出力エンコードを検査で守る

deliver プロファイル全体を、観点を分けた独立レビュアー 4 本（maker≠checker・ミューテーション実測つき）で
レビュー。確認された正しさ/セキュリティ欠陥（ブロッカー）を修正し、いずれも回帰テストで (c)→(b) に上げた。

- **xlsx の数式注入**（`xlsx.py`）：作業名・チーム・担当・案件名が `=+-@` 等で始まると openpyxl が生きた数式
  セル（data_type 'f'）として保存し、クライアントの Excel で式が走る。`_put` で該当文字列を data_type 's'
  （文字）に固定して無害化。
- **`dayAt` のタイムゾーン 1 日ずれ**（`render.py` 編集JS）：`new Date(first+'T00:00:00')`（ローカル解釈）＋
  `toISOString()`（UTC）で JST など UTC+ ではクリック日の前日が正本に書かれる。パース・加算・出力を UTC で
  統一（`'…Z'`＋`setUTCDate`）。
- **手動行の二重掲載で進捗過大**（`wbs_lint.py`）：1 つの手動行を 2 つの節が指すと 2 行になり done/total が
  二重計上されるのに検査が `entry.work` しか見ていなかった。`entry.row` も重なり検査に載せた。
- **出力エンコードの無検査**（重大寄り）：`_esc` を無効化しても全テスト緑だった＝HTML 注入の守りが (c)。
  作業名/出来事名/レーン名の生タグ・属性抜け出しが出力に生で現れないことを見るテストを追加。xlsx 側も同様に
  数式注入テストを追加。

ミューテーション：4 ガードとも「fix を外す→対象テストが RED」を実測（xlsx/esc/lint はソース改変、dayAt は
構造ガード）。※ミューテーションの後始末に `git checkout` を使うと未コミットの本修正まで戻るので、本修正は
コミット後に検証し直した（教訓）。

## 受け入れ基準
- [x] xlsx が `=+-@` 始まりの利用者文字列を data_type 's' で書く（数式にしない）。
- [x] 閲覧用・編集用の HTML で利用者文字列が生タグ・属性抜け出しにならない（`_esc` 経由）。
- [x] 同じ手動行を 2 つの節が指すと wbs_lint が error にする。
- [x] `dayAt` が UTC でそろえて日付を出す（JST で 1 日ずれない）。
- [x] 4 ガードとも対象テストがミューテーションで RED（fix 無しで落ちる）。
