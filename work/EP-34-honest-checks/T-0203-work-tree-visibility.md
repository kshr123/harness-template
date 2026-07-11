---
id: T-0203
kind: task
status: done
title: work の不可視領域と正体不明の md を error にする
requirements: [REQ-001]
created: 2026-07-11
depends_on: []
verified_by:
  - tests/test_pm.py::test_work_tree_orphan_dir_hides_unit_is_error
  - tests/test_pm.py::test_work_tree_unknown_md_is_error
  - tests/test_pm.py::test_work_tree_artifact_md_is_ok
  - tests/test_pm.py::test_work_tree_nested_unit_with_item_chain_is_ok
  - tests/test_pm.py::test_work_tree_lightweight_unit_directly_in_work_is_ok
---
# T-0203 work/ の不可視領域を無くす

## 実測した欠陥（再現済み）
`pm.lint` の木は `_load_dir` が item.md を持つディレクトリしかたどらない。よって：
- **item.md の無いディレクトリ配下の作業単位は、全 PM 検査から消える**。`verified_by` の無い done も素通り
  する（`work/orphan/T-0099.md` に done を置いても error が出ないことを実測）。
- 命名が `UNIT_FILE` に一致しない `.md`（例 `T0001.md`＝ハイフン無し）も同様に不可視。

## 直したこと（対象集合はファイルシステムから機械的に導く＝(b) の条件）
`work_tree_lint(root)` を新設し、木を使わず `work/` 以下の全 `.md` を走査する。error は 2 種類：
1. `UNIT_FILE` に一致する `.md` を含むのに、item.md の鎖が `work/` まで途切れているディレクトリ
   （＝不可視の単位）。可視判定は `_dir_is_visible`：`work/` 自身か、「item.md を持ち、かつ親も可視」の
   ディレクトリだけが木に載る、という `_load_dir` の走査規則を写したもの。
2. `UNIT_FILE` にも成果物のファイル名（`_ARTIFACT_FILES`）にも一致しない `.md`（＝正体不明を黙認しない）。

成果物の許容パターンは既存の `pm.py` の `_ARTIFACT_FILES` を使う。実在した `DESIGN.md`（EP-06/09/10/11 の
設計メモ・既知の成果物）は正体不明ではないので `_ARTIFACT_FILES` に `DESIGN.md` を加えた（黙って通すのでは
なく、既知の成果物として明示登録する）。

`work_tree_lint` は `pm.lint` の末尾から呼ぶ（`pm.lint` は `PM_CHECKS` の一員なので verify に載る）。

## テスト（先に書いた・期待値は入力の構成から導く）
- `test_work_tree_orphan_dir_hides_unit_is_error`：item.md 無しの子ディレクトリの done（verified_by 無し）が
  error になる。統合として `pm.lint` 経由でも同じ error が出ることも確かめる。
- `test_work_tree_unknown_md_is_error`：`T0001.md` のような正体不明 `.md` が error。
- `test_work_tree_artifact_md_is_ok`：`DESIGN.md`・`notes.md` は許容（error にしない）。
- `test_work_tree_nested_unit_with_item_chain_is_ok`：item.md の鎖が続く入れ子の単位は可視＝error にしない。
- `test_work_tree_lightweight_unit_directly_in_work_is_ok`：`work/` 直下の軽い単位ファイルは可視。

## ミューテーション実測（guard を壊すと RED）
- 不可視ディレクトリの error 生成を外す → `test_work_tree_orphan_dir_hides_unit_is_error` が RED。
- 正体不明 `.md` の error 生成を外す → `test_work_tree_unknown_md_is_error` が RED。
