---
id: T-0246
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 2
requirements: [REQ-006]
depends_on: [T-0245]
verified_by:
  - tests/test_deliver_stamp.py::test_a_parent_row_gets_a_toggle_and_children_are_addressable
  - tests/test_deliver_stamp.py::test_collapsed_rows_still_print
  - tests/test_deliver_stamp.py::test_the_fingerprint_follows_the_values_on_the_page
  - tests/test_deliver_stamp.py::test_the_stamp_names_the_commit_and_the_time
  - tests/test_deliver_stamp.py::test_without_git_the_stamp_says_unknown_and_nothing_is_refused
  - tests/test_deliver_stamp.py::test_export_refuses_while_the_tree_is_dirty
  - tests/test_deliver_stamp.py::test_draft_is_allowed_but_says_so_on_the_page
  - tests/test_deliver_stamp.py::test_a_clean_tree_exports_with_its_provenance
---
# T-0246 提出物として渡せる体裁にする（折りたたみ・印刷・由来）

## 作ったもの

- **折りたたみ** … 親の行の WBS 番号の横に取っ手を置く（表題の列は直せる欄なので、そこに置くと押すたびに
  編集が始まってしまう）。畳んだ行は**隠れるだけで本文から消えない**。印刷では CSS が必ず戻す
  ＝畳んだまま刷って白紙のフェーズを渡す事故が、そもそも起こらない形にした（気をつける話にしない）。
  入れ子の親を開き直したとき、閉じたままの中間の親の配下は開かない。
- **由来の刻印**（`stamp.py`）… 見出しに「コミット・生成日時・内容の指紋」を出す。内容の指紋は表に出ている
  値そのものから作るので、コミットが同じでも中身が違う／コミットが違っても中身は同じ、を見分けられる。
  git が無い場所ではコミットを「不明」にして拒否はしない（git を前提にしない）。
- **未コミットのときの拒否** … 既定では出力しない（刻んだコミットが実際の中身と食い違う＝由来が嘘になる）。
  定例の直前に 1 行直してすぐ出す実務があるので `--draft` を残したが、そのときは生成物に「下書き（未コミットの
  変更を含む）」と出る＝既定を不合格側に置いたまま、逃げ道を見て分かる形にした。

## 受け入れ基準

- [x] 畳んだ状態で印刷しても、畳まれた行が出力に含まれるか。
- [x] 未コミットの変更がある状態で既定の出力が失敗するか（刻んだコミットが嘘にならないか）。
- [x] 下書き指定で出したとき、下書きであることが生成物から分かるか。
- [x] 同じ木から出した生成物の内容の指紋が一致し、値を変えると変わるか。
