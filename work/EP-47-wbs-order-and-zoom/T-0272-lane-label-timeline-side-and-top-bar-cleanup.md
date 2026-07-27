---
id: T-0272
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0271]
verified_by:
  - tests/test_deliver_geometry.py::test_the_lane_label_slides_and_stops_at_the_work_column
  - tests/test_deliver_geometry.py::test_the_top_bar_is_pared_down_and_the_legend_is_grouped
  - tests/test_deliver_geometry.py::test_a_finished_row_recedes_with_a_muted_fill
---
# T-0272 レーン見出しを時系列側へ・上部の整理・凡例の 2 群化・空白の罫線撤去

見た指摘への対応（領域と読みやすさの詰め・第 2 弾）。

- **レーン見出しを時系列の側へ**：既定はガントのすぐ左（右寄せ）に置く（帯の◆○のそばに名前）。中身の span を
  `position:sticky; left:64px`（作業列の位置）にし、横スクロールすると左へ流れて作業列のあたりで止まる
  ＝読めなくならない。セル自体は流れる（右寄せの起点＝ガントの左端を保つ）。
- **空白の罫線を撤去**：時間軸の左側の空セル（何も無いところ）から罫を全部消す（横罫・グループの強い縦線 .gs・
  固定列の強い縦線）。黒い縦線が空白に走る違和感を無くす。
- **レーンをさらに低く**：`--lane-h` 16px→14px、見出しの文字も 10px に（主役でないので占有を抑える）。
- **上部を整理**：日付の見出しを「基準日」→「本日」に（意味が分かる語に）。「＋出来事」ボタンを撤去
  （登録はレーンの空きクリックに一本化）。表示切替（列・レーン）のボタンを静かな見た目に（オン＝淡い地色。
  青で主張させない。主操作の時間軸の月/週/日だけはっきり示す）。
- **凡例を 2 群に**：羅列でなく「記号」「行の状態」の見出しで括る。細かい説明はホバー（title）へ逃がす。
  完了は実際の面＋淡い文字のチップで見せる。

## 受け入れ基準
- [x] レーン見出しが既定で時系列側（右寄せ）に出て、span が sticky・left:64px で作業列のあたりに止まる。
- [x] 見出しの日付が「本日」表記、「＋出来事」ボタンが無い、凡例が「記号」「行の状態」の 2 群。
- [x] 時間軸の左の空セルに罫が無い（横も、強い縦線も）。
- [x] 完了行が面＋淡い文字で退く不変条件を保つ。
