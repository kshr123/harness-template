---
id: T-0258
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: []
depends_on: [T-0257]
verified_by:
  - tests/test_deliver_roster.py::test_a_name_is_added_whatever_the_yaml_looks_like
  - tests/test_deliver_roster.py::test_saving_a_new_name_puts_it_in_the_roster
  - tests/test_deliver_roster.py::test_saving_a_team_puts_it_in_the_team_roster
  - tests/test_deliver_roster.py::test_clearing_a_field_does_not_touch_the_roster
  - tests/test_deliver_roster.py::test_the_edit_page_offers_the_roster_as_choices
  - tests/test_deliver_roster.py::test_a_manual_row_assignee_is_written_as_a_list
---
# T-0258 チーム・担当者を名簿から選ぶ

自由入力だと表記ゆれが起きる（同じ人が別人として並ぶ・集計が割れる）。案件の名簿を持ち、画面ではそこから選ぶ。

## 作ったもの
- 上書きファイルに案件の名簿（`teams`・`members`）。
- 作業単位に `team`（`owner` と対称の任意欄）。これが無いとチームの列が常に空になり、列として使えない。
- 画面のチーム・担当の欄を選択に変え、名簿を選択肢として渡す。名簿に無い名前を入れる口も残す。
- **入れた名前は名簿にも足す**（選ぶ先と実際に使われている名前がずれない）。追記も 1 行だけの書き換えで、
  書き方（1 行の並び・箇条書き・キーが無い）は人が書いたものに合わせる。
- 手動行の担当は一覧の欄なので、選んだ 1 人を並びとして書く（型を崩さない）。

## 受け入れ基準
- [x] 名簿の書き方に関わらず名前を足せるか（1 行の並び・箇条書き・キーが無い・ファイルが無い）。
- [x] 同じ名前を 2 度入れても増えないか。名簿を足してもコメント・他の設定が動かないか。
- [x] 画面の欄が名簿を選択肢として持っているか。渡す生成物には選択肢が入らないか。
- [x] 空にする操作で名簿が増えないか。
