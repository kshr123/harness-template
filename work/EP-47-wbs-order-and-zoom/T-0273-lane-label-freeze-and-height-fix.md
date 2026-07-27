---
id: T-0273
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0272]
verified_by:
  - tests/test_deliver_geometry.py::test_the_lane_label_is_frozen_at_the_work_column
  - tests/test_deliver_geometry.py::test_lane_rows_are_exactly_one_lane_height_so_sticking_does_not_break
---
# T-0273 レーン見出しを固定列に戻す（横スクロールの崩れ）・帯の高さを揃える（縦スクロールの崩れ）

T-0272 で見出しを「時系列側で追従」させたら 2 つ崩れたので直す。

- **横スクロールの崩れ**：追従（span sticky）だと、作業列の位置を**超えて**さらに左へ流れ、かつガントの◆○が
  固定領域へ**漏れて**重なった。原因は、見出しが流れるセルの中の span で、そのセルの右端（ガント境界）に
  引きずられて left:64 を割り込む＋固定領域を覆う不透明セルが無いこと。**見出しを作業名と同じ扱いに戻す**：
  `ms-label` を colspan 2（No.＋作業）・`position:sticky; left:0`・不透明・z-index を同じ行の他セルより上に。
  作業列で必ず止まり、ガントが下に潜っても◆○を覆って漏らさない（構造で決まる）。ガントとの間に空きが出るのは
  作業名と棒の間の空きと同じ＝ガントの標準の見え方。
- **縦スクロールの崩れ**：見出しセルにデータ行の上下余白（5px）が残り、行の実寸（約24px）が段の送り
  `--lane-h`（14px）とずれて、貼り付いたとき段が重なって潰れた。**帯の全セルを縦余白 0・高さ `--lane-h`
  ちょうど**にして、段の送りと実寸を同じ変数に縛る（ずれようがない）。

## 受け入れ基準
- [x] `ms-label` が sticky・left:0・z-index:6（他セル 4 より前面）＝作業列で止まり◆○を漏らさない。
- [x] `tr.msrow > td` の高さが `--lane-h` で、段の送り `--laneidx * --lane-h` と同じ変数＝縦スクロールで崩れない。
- [x] 横スクロール（週・日）で見出しが作業列を超えず、◆○が固定領域に入らない（ヘッドレスで確認）。
