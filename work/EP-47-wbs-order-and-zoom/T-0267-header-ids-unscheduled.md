---
id: T-0267
kind: task
status: done
created: 2026-07-24
closed: 2026-07-24
start: 2026-07-24
due: 2026-07-24
effort_days: 1
requirements: []
depends_on: [T-0266]
verified_by:
  - tests/test_deliver_render.py::test_unscheduled_row_is_marked
  - tests/test_deliver_geometry.py::test_the_output_is_a_complete_document
---
# T-0267 見出しの固定・ID 非表示・未日程一覧の撤去・曜日左揃え

実際に描画して見た指摘のうち、明確な 4 点。

- **見出しを縦スクロールでも固定**：表領域に高さ（`max-height:calc(100vh - 150px)`）を与えて中でスクロール
  させる。以前は本文を縦スクロールすると 2 段見出しが流れて消えた（container-type が sticky をコンテナ内に
  閉じ込めるため、コンテナ自体をスクロール器にする）。印刷では解除。
- **作業単位の ID（EP-/T-/W-）を閲覧で隠す**：クライアントに関係ないので `.ref` を非表示に。編集の参照用に
  data-ref 属性は残す。
- **未日程の一覧を撤去**：クライアント向けに末尾の「未日程（N件）」は出さない（日程の無い行はガントが空なので
  見れば分かる。行の区別クラスは残す）。
- **曜日を左揃え**に（この後 T-0268 で 3 段の整列とあわせて仕上げ）。

## 受け入れ基準
- [x] 縦スクロールで 2 段見出しが残るか。
- [x] 閲覧で作業単位の ID が出ないか（属性では持つか）。
- [x] 未日程の一覧が出ないか。
