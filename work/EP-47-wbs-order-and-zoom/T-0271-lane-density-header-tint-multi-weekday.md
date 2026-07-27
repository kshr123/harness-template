---
id: T-0271
kind: task
status: done
created: 2026-07-27
closed: 2026-07-27
start: 2026-07-27
due: 2026-07-27
effort_days: 1
requirements: []
depends_on: [T-0270]
verified_by:
  - tests/test_deliver_geometry.py::test_the_lane_label_slides_and_stops_at_the_work_column
  - tests/test_deliver_geometry.py::test_a_finished_row_recedes_with_a_muted_fill
  - tests/test_deliver_geometry.py::test_no_row_fill_reaches_into_the_gantt
---
# T-0271 レーンの密度・見出しの地色・完了の退け方・曜日の複数選択

見た指摘への対応（領域と視認性の詰め）。

- **レーンを低くする**：1 本 20px → `--lane-h`=16px（唯一の出どころ＝CSS・JS・初期 scroll_vars）。データ行との
  律動差を保ちつつ、マイルストーン・定例・インナーの占有領域を抑える。
- **レーン見出しを固定列へ**：見出し（マイルストーン等）を No.＋作業の固定列に貼り付けて右寄せ＝横スクロールで
  左へ流れて固定列の下に潜って消えるのを止める。同じ行の他セル（z-index:4）より前面（z-index:6・詳細度も上げる）
  に置く。子結合子は使わない（ガント列への地色を止める検査に、非ガント専用の .ms-label を巻き込まないため）。
- **レーンの罫の整理**：帯**同士**は薄い横罫（--line）で分ける。時間軸の左側の空セルは下罫を引かない＝
  マイルストーン帯の上の罫は日付の下（ruler-cell）だけに出す（左の空白まで区切ると注釈帯が大きく見える）。
- **作業表の見出しを一段濃く**：まとまり見出し＋列名の地色を --head に（時間軸・レーンの --sec と別の帯に見せ、
  表の頭だと分かる）。
- **完了をもっと退ける**：面を少し淡く（--done-row）、文字を専用の淡い灰（--done-ink）に＝行の面と区別しつつ
  インパクトを下げる。
- **曜日の複数選択**：出来事フォームの曜日をチェックボックス群に。BYDAY にカンマで並ぶ（週 2 回＝`BYDAY=MO,WE`。
  毎月第N は各曜日に第N が付く＝`BYDAY=2MO,2WE`）。既存規則の BYDAY から曜日を復元、無ければ初回の曜日。

## 受け入れ基準
- [x] レーン見出しが sticky・left:0・z-index:6 で固定される（横スクロールで消えない）。
- [x] 完了行が --done-row の面＋--done-ink の文字で、行の面（--sec）と区別できる。
- [x] 行の地色がガント列に当たらない不変条件を保ったまま（検査を通す）。
- [x] 曜日を複数選ぶと BYDAY がカンマ区切りで組み上がる（ヘッドレスで確認）。
