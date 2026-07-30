---
id: T-0275
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0274]
verified_by:
  - tests/test_deliver_geometry.py::test_the_whole_task_table_is_frozen_and_only_the_calendar_scrolls
  - tests/test_deliver_geometry.py::test_the_lane_label_hangs_from_the_panel_edge_without_entering_the_calendar
---
# T-0275 左の作業表をまるごと固定する（標準のガント）＝レーン見出しが横スクロールで隠れない

見た指摘への対応：レーン見出しが「作業列を超えると隠れてしまう」。

これまで固定していたのは No.＋作業の 2 列だけで、間の列（チーム/担当/状態/予定/実績）は横スクロールした。
そのため横に流すとカレンダーの左端が固定列の右まで来て、そこに見出しを出すと今度はカレンダーに被る＝
「隠れる」か「侵食する」のどちらかにしかならなかった（幾何学的な行き詰まり）。

- **解決＝作業表をまるごと固定**（標準のガント：作業表は据え置き、時間軸だけ横スクロール）。非ガントのセルを
  すべて `position:sticky` にし、各列の `left` は JS（`freezePanel`）が各行でガント列の手前まで幅を積み上げて
  入れる（作業名は可変幅・チーム/担当は隠せるので固定値にしない。列トグル・リサイズで入れ直す）。こうすると
  作業表の右端＝カレンダーの左端の位置が横スクロールで変わらないので、見出し（`ms-label`・右寄せ）は
  カレンダーの左隣に**常に**留まる（隠れない・カレンダーに被らない）。
- **直したバグ**：見出しセルが `thead tr.msrow > td { z-index:4 }`（詳細度が高い）に負けて z-index 4 になり、
  横スクロールで滑ってくるカレンダー（ms-track・同じ 4・DOM で後）に上書きされて消えていた。詳細度の高い
  専用規則（`thead tr.msrow td.ms-label`）で z-index 6 に上げて、カレンダーより前面に固定した。
- 印刷は非ガントを `position:static` に戻す（紙はスクロールしない）。

## 受け入れ基準
- [x] 非ガントのセルがすべて sticky（作業表まるごと固定）で、ガント列だけ横スクロールする。
- [x] 横スクロール（週・日）でレーン見出しがカレンダーの左隣に留まり、隠れない・被らない（ヘッドレスの当たり判定＝ms-label／実測で位置不動）。
- [x] 作業名の可変幅・チーム/担当の表示切替でも left が入れ直る（freezePanel を recount とリサイズで呼ぶ）。
