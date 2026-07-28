---
id: T-0276
kind: task
status: done
created: 2026-07-28
closed: 2026-07-28
start: 2026-07-28
due: 2026-07-28
effort_days: 1
requirements: []
depends_on: [T-0275]
verified_by:
  - tests/test_deliver_geometry.py::test_the_lane_label_hangs_from_the_panel_edge_without_entering_the_calendar
  - tests/test_deliver_geometry.py::test_the_whole_task_table_is_frozen_and_only_the_calendar_scrolls
---
# T-0276 レーン見出しが横スクロールの端でカレンダーに侵食するのを直す

作業表をまるごと固定した（T-0275）のに、横スクロールの端でレーン見出しがカレンダーへ食い込んでいた。

- **原因 1（幅のずれ）**：レーン行は colspan セル（ms-frozen 2 + ms-label 9）で作っていたが、colspan セルの
  実幅がデータ行の列合計と一致しない（端まで送ると 37px 広かった）。右寄せの見出しはその広いセルの右端＝
  カレンダーの中に出ていた。→ **レーン行をデータ行と同じ列構成**（各列に空セル 1 つ）にして幅を 1px も
  違えないようにし、見出しは最後の非ガントセルの `right:0`（＝パネル右端）から**左へぶら下げる**（絶対配置）。
  右へは一切出ない（端まで送っても overshoot=0 を実測）。
- **原因 2（z 漏れ）**：レーンの空セルが `thead tr.msrow > td { z-index:4 }`（詳細度が高い）に負けて z4 になり、
  横スクロールで滑ってくるカレンダー（ms-track・同 4・DOM で後）が空セルの上に◆○を描いていた。→ 詳細度の
  高い専用規則（`thead tr.msrow td.ms-cell`／`td.ms-anchor`）で z-index を 6 に上げ、カレンダーより前面に固定。
- 見出しの絶対配置の基準は sticky セルそのもの（relative を足すと固定が外れて流れるので足さない）。

## 受け入れ基準
- [x] レーン行が colspan を使わずデータ行と同じ列構成（幅が 1px もずれない）。
- [x] 端まで横スクロールしても見出しの右端＝パネル右端（overshoot=0・実測）＝カレンダーに侵食しない。
- [x] 端まで横スクロールしてもパネル内にカレンダーの◆○が漏れない（パネル全幅を当たり判定して NONE）。
