---
id: T-0270
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0269]
verified_by:
  - tests/test_deliver_geometry.py::test_lanes_sit_in_the_header_not_between_columns_and_data
  - tests/test_deliver_geometry.py::test_the_milestone_lane_is_always_present_when_editable
  - tests/test_deliver_adder.py::test_a_lane_milestone_takes_a_name_and_a_day
  - tests/test_deliver_adder.py::test_a_milestone_through_the_server_writes_to_the_edit_copy
---
# T-0270 見出しの縦の並びを 時間軸→レーン→作業表 にし、帯ごとに登録の既定を分ける

見た指摘への対応（前の版ではレーンを見出しの末尾＝列名とデータの間に置いていた）。

- **見出しの縦の並び**を「時間軸 → マイルストーン等のレーン → 作業表（まとまり見出し・列名・データ）」に。
  ガントの「ものさしが上・読み取り値が下」をそのまま縦の並びにする。時間軸は専用の行（`tr.ruler`）に出し、
  ガントのまとまり見出し＋列名のセルは 2 段ぶちぬき（`gantt-body`）。sticky の `top` は各段の高さ（時間軸
  45px・レーン 1 本 20px・見出し 22px）の累積で決める。レーン（注釈帯）と作業表の領域境界は最強の 2px 罫。
- **帯ごとに登録の既定を分ける**（クリックの意味はそこに住む値で決まる）。マイルストーン帯のクリック＝その日の
  マイルストーンを登録（名前＋日付のフォーム／書き戻し先は `work/`＝`add_milestone`）、出来事の帯のクリック＝
  その帯の出来事を登録（そのレーン名で `openEvent`）。マイルストーン帯は編集面では 0 件でも出す（クリックの的）。
- **完了の面をもっと濃い灰に**（`--done-row` を #c2c8d0／暗色は #3a414c）。行の地色（節の面 --sec）と区別が
  つかない、という指摘への対応。

## 受け入れ基準
- [x] thead の行順が 時間軸（ruler）→ レーン（msrow）→ まとまり見出し（grp）→ 列名、になっているか。
- [x] 編集面ではマイルストーンが 0 件でもマイルストーン帯が出るか（閲覧用は 0 件なら出さない）。
- [x] マイルストーン帯のクリックで、名前とクリックした日でマイルストーンを足せるか（基準日ではなく指した日）。
- [x] /milestone が編集の場に書き、正本は取り込みまで無傷か。
