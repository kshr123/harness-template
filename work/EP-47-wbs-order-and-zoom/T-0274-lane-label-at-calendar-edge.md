---
id: T-0274
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0273]
verified_by:
  - tests/test_deliver_geometry.py::test_the_lane_label_sits_at_the_calendar_edge_and_covers_leaks
  - tests/test_deliver_geometry.py::test_lane_rows_are_exactly_one_lane_height_so_sticking_does_not_break
---
# T-0274 レーン見出しをカレンダーの左端に置く・帯の高さ潰れを確定的に直す

見た指摘への対応（目線移動と縦スクロールの潰れ）。

- **目線移動**：見出しを作業列（左端の固定列）に置くと、◆○（カレンダー内）から遠くて目線が大きく動く。
  → 見出し（`ms-name`）を**カレンダー（ガント）の左端**に置く＝◆○のすぐ左。ガント列を `overflow:visible` に
  して中の `ms-name` を sticky にし、横スクロールでは見えている左端（`--frozen-w`＝固定列の実測幅を JS で渡す）
  に貼り付いて止まる。ガント列は広いので左へ流れきらない＝作業列超え・記号漏れが起きない。記号と今日線は
  内枠 `ms-clip`（absolute・overflow:hidden）でクリップする（sticky は overflow:hidden の中で効かないため、
  見出しはクリップの外）。固定列（No.＋作業）は空の不透明セル `ms-frozen` で覆い、ガントが下へ潜っても◆○を
  漏らさない。
- **縦スクロールの潰れ（確定版）**：table の td の height は最小値なので、既定の行間（line-height）のままだと
  行が `--lane-h`（14px）より高くなり、貼り付いたとき段が重なって潰れた（前タスクの直しでは残っていた）。
  帯の全セルに `line-height:1` を当て content を font 分（< --lane-h）に抑え、段の送りと実寸を同じ 14px に
  そろえた（ヘッドレスで各帯の実寸＝14px・送り＝14px を実測して確認）。

## 受け入れ基準
- [x] 見出しが初期位置でカレンダーの左端（◆○のそば）に出る。
- [x] 横スクロールで見出しがカレンダーの見えている左端で止まり、作業列を超えない・◆○が固定列へ漏れない（週・日で確認）。
- [x] 縦スクロールで各帯の実寸が 14px・送りが 14px でそろい、段が潰れない（ヘッドレスで実測）。
