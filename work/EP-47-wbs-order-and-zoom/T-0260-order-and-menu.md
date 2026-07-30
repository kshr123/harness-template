---
id: T-0260
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_deliver_adder.py::test_a_sibling_can_be_placed_above_or_below
  - tests/test_deliver_adder.py::test_the_written_order_is_spaced_so_more_fit_between
  - tests/test_deliver_adder.py::test_a_project_without_any_order_keeps_the_filename_order
  - tests/test_deliver_adder.py::test_the_edit_page_carries_what_the_menu_needs
---
# T-0260 順序を持たせ、右クリックで上・下に足せるようにする

## 作ったもの
- 作業単位に `order`（同じ置き場での並び順）。並びは `order` → ファイル名の順にした。**書いていない案件は
  これまでどおりファイル名の順**なので、既定の見え方は変わらない。
- 右クリックの操作を作り直した。見出しに「WBS 番号・名前・第何階層か」を出し、足す向きを階層つきで並べる
  （この行の上／下＝同じ階層、この行の中＝1 つ下の階層、いちばん上の階層＝区切って離す）。
  **最上位に足すのと下の階層に足すのは意識が変わる操作**なので、同じ並びに埋めない。
- 行に置いていた「＋」を撤去（操作は右クリックに寄せる）。

## なぜ順序の置き場が要るか
並びはファイル名の順＝実質 ID 順で、ID は既存の最大＋1 でしか採れない。だから「この行の上に足す」は
順序を書かないと表現できない（足したものが必ず最後に来る）。順序は日程からも ID からも導けない
**人が決める情報**なので、置き場を作った。最初の挿入でその置き場の並びを 10 刻みで書き出し、新しい行には
その間の値を与える（以後の挿入は 1 行の書き足しで済む）。

## 受け入れ基準
- [x] 「上に足す」「下に足す」がその位置に入るか。
- [x] 並び順が詰めずに刻んで振られるか（次の挿入が入る余地があるか）。
- [x] 順序を書いていない案件の並びが、これまでどおりファイル名の順か。
- [x] 行に「＋」が無く、右クリックに要る情報（階層・足せる先）が行に載っているか。
