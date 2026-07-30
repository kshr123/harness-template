---
id: T-0295
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-49]
verified_by:
  - tests/test_profiles.py::test_promotion_rollback_is_owned_by_both_ds_and_agent
  - tests/test_doclint.py::test_case_area_path_reference_is_not_flagged_when_absent
  - tests/test_doclint.py::test_non_case_area_missing_path_is_still_an_error
---
# T-0295 clone-simulation を緑に（プロファイル所有・案件領域パスの免除）
fork 模擬（案件領域を白紙化＋`profiles=[]`＋素の uv sync）で verify が 2 つの理由で落ちる：
- `test_promotion_rollback.py` が numpy/sklearn（DS）と agent を module-top で import するのに、どのプロファイルの
  `test_globs` にも入っていない → ds/agent 無効時に収集エラー。`test_promotion_characterization` と同じく
  ds・agent の両方に所有させる（両方が要るテストは片方でも無効なら収集から外れる）。
- doclint の相対パス実在検査が `docs/wbs.yaml` を「存在必須」と見るが、これは init-project が白紙化する
  **案件領域ファイル**＝fresh clone に無くて当然。durable な docs（AGENTS 等）がこれを指すのは壊れリンクでは
  ない。doclint が `CASE_AREA_ROOTS`（正本 = init_project）配下のパスを実在検査から除外する。

## 受け入れ基準
- [x] ds か agent が無効なら `test_promotion_rollback.py` が収集から外れる（disabled_profiles の glob に入る）。
- [x] doclint が案件領域パス（例 `docs/wbs.yaml`）の不在を error にしない一方、案件領域外の不在パスは従来どおり error。
- [x] fork 模擬（ローカル再現）で verify が緑。
