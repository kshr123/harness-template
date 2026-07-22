---
id: T-0242
kind: task
status: done
title: upstream merge が案件領域を汚染しないよう template-copy を訂正し (b) で固定する
created: 2026-07-22
closed: 2026-07-22
depends_on: []
verified_by:
  - tests/test_template_copy.py::test_upstream_merge_keeps_case_area_ours
  - tests/test_template_copy.py::test_merge_recipe_does_not_commit_shared_file_conflict
  - tests/test_template_copy.py::test_merge_recipe_areas_cover_case_area_roots
  - tests/test_init_project.py::test_declared_scrub_targets_are_under_case_area_roots
  - tests/test_init_project.py::test_scrub_empties_project_area_and_keeps_core
---
# T-0242 本体→案件 merge の案件領域汚染を塞ぐ

## なぜ
`docs/template-copy.md` 2 節は「本体領域と案件領域はファイルレベルで排他なので merge は案件のファイルに触れない・
競合が起きうるのは pyproject/uv.lock の2つだけ」と偽の保証(a)を書いていた。だが `work/`・`issues/` は本体
（テンプレート）も自分の開発履歴として持つ（テンプレートは自分自身を最初の案件として work/ にコミットし続ける）。
scratch git で実測：fork が `git merge upstream/main` すると本体の EP-99 が案件の work/ に無音流入し、init-project
で消した EP-01 を本体が変更していれば modify/delete で復活する。本体改良（src/harness/…）だけ欲しいのに案件領域が
汚染される＝条件1（黙って汚染しない）×条件4（案件を重ねるほど強くなる＝配布経路）の交点の欠陥。前2回の PM 検討は
どちらも「fork の瞬間」だけ見て「fork 後の時間発展」を見落としていた。

## 何を
- `template-copy.md` 2 節：偽の主張を訂正し、本体も work/issues を持つ事実と汚染経路を明記。
- `template-copy.md` 4 節：merge 後に案件領域を fork(HEAD) の版へ統一する復旧レシピを記載（`git rm --cached` で
  index から外す→`git checkout HEAD --` で自分の版に戻す→未追跡の本体由来を消す）。対象集合 AREAS は init-project の
  白紙化対象と同じ（正本は init_project.py・二重管理しない）。実測で本体改良は入り案件領域は汚れないことを確認。
- `template-copy.md` 5 節＋harvest スキル：還流候補を洗う `git log upstream/main..HEAD -- 本体領域` を1行（台帳/bot なし）。
- `init_project.py`：scrub の取りこぼし修正＝`INV-*` を白紙化対象に追加。

## 検証
`test_upstream_merge_keeps_case_area_ours`（integration）＝fork→本体前進→merge を実際に git で再生し、
案件領域が fork 側のまま（EP-99 流入せず・EP-01 復活せず・issues 汚染なし）かつ本体改良（core v2）は取り込めることを
実測で固定。散文の復旧レシピが退行すれば赤くなる（保証 (b)）。`test_scrub_empties_project_area_and_keeps_core` に
`INV-*` の白紙化を追加。`uv run verify` 緑。

maker≠checker（別 fable）で 2 巡：初回に7件（高2：競合マーカーの自動コミット／CI で git identity 無し）を指摘され
全件修正（競合は自動 commit せず人へ残すガード＋その (b) テスト・doc から recipe を抽出して実行し正本1つに・
クリーンツリー前提を fail-closed 化 等）。再レビューで「AREAS 一致テストが scrub の効果を fixture で見ており drift を
見逃す」と再指摘され、案件領域の根の正本 `CASE_AREA_ROOTS`（init_project.py の1か所）を定義し scrub をデータ駆動化
（`declared_scrub_targets()`）、宣言を静的検査する形へ。連鎖＝宣言 ⊆ 定数（test_init_project）／doc AREAS ⊇ 定数
（test_template_copy）で、どのホップの drift も赤くなる（reviewer の drift シナリオが RED になることを実測）。全7件クローズ。
