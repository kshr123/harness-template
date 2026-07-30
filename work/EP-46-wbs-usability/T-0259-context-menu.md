---
id: T-0259
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: []
depends_on: [T-0258]
verified_by:
  - tests/test_deliver_remover.py::test_a_leaf_unit_is_removed
  - tests/test_deliver_remover.py::test_a_unit_with_children_is_refused
  - tests/test_deliver_remover.py::test_an_emptied_folder_unit_can_then_be_removed
  - tests/test_deliver_remover.py::test_removing_something_others_depend_on_is_refused
  - tests/test_deliver_remover.py::test_a_manual_row_and_the_section_pointing_at_it_go_together
  - tests/test_deliver_remover.py::test_removing_through_the_server_needs_the_token
  - tests/test_deliver_remover.py::test_rows_carry_what_the_menu_needs
---
# T-0259 行の右クリックで足す・直す・消す

操作が画面から分からなかった（足すのは「＋」だけ、消す手段が無い）。行を右クリックして選ぶ形にする。

## 作ったもの
- 右クリックの操作：この下に足す／同じ階層に足す／名前を変える／消す。足し先は行が持っている
  （この下＝自分がフォルダの単位のとき、同じ階層＝いちばん近い親のフォルダの単位）ので、画面側で
  組み立て直さない。
- 消す（`remover.py`）：作業単位はそのファイル（フォルダの単位ならフォルダごと）、手動行は上書きファイルの
  その塊と**それを指している節の項目も一緒に**取る（片方だけ残すと参照切れになる）。空になった一覧のキー行も
  落とす（値が空になって読めなくなるため）。
- 配下を持つ単位は消さない（何が消えるか画面から見えないまま失うのを防ぐ）。先に配下を消す。
- 書き込む口はどれも、**作業単位の検査と WBS の検査の両方**を書く前後で見比べ、増えた指摘だけを拒否の
  理由にする。WBS の検査だけを見ると、参照が切れた `depends_on` のような作業単位の側の壊れ方を通してしまう。

## 受け入れ基準
- [x] 末端の単位を消せるか。配下を持つ単位は理由を出して断るか。
- [x] 配下を先に消せば、フォルダの単位もフォルダごと消せるか。
- [x] 他が先行として指している単位を消そうとしたとき、書き戻して断るか。
- [x] 手動行を消すと、それを指している節の項目も消えるか。上書きファイルが読める状態のままか。
- [x] 合言葉なしでは消せないか。右クリックの操作に要る情報が行に載っているか。
