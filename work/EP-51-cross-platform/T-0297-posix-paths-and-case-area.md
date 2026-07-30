---
id: T-0297
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-50]
verified_by:
  - tests/test_conventions.py::test_stringifying_a_relative_path_without_as_posix_is_flagged
  - tests/test_doclint.py::test_case_area_subtree_is_exempt_but_boundary_sibling_is_not
  - tests/test_doclint.py::test_case_area_glob_matches_per_segment_not_across_slash
  - tests/test_deliver_session.py::test_input_keys_are_posix_not_backslash
---
# T-0297 リポ相対パスの `\` 依存を潰す＋doclint 免除の厳密化（ISS-0019）
リポ相対パスを `.as_posix()` を挟まず文字列化していた5箇所（pm・agent/lint・deliver/session の指紋キー・ds/cli×2）を
`.as_posix()` に統一し、Windows で `\` にならないようにする。再発を防ぐため conventions に規則5（`str(x.relative_to(y))`
と f-string の `{x.relative_to(y)}` を error にする ast 検査。別名束縛の形は見逃す＝束ねる箇所での `.as_posix()` は
レビュー観点、と明記）を追加。加えて doclint の案件領域免除を `fnmatch`（`*` が `/` を跨ぐ・Windows で大小無視）から
セグメント境界一致＋`fnmatchcase` に厳密化（`docs/structure-review-*.md` が入れ子を覆わない・OS で挙動が変わらない）。

## 受け入れ基準
- [x] 5 箇所の相対パス文字列化が `.as_posix()`（Windows で `\` にならない）。
- [x] conventions 規則5 が `str(x.relative_to(y))`・`{x.relative_to(y)}` を error にし、`.as_posix()` 版は通す。
- [x] doclint 免除がセグメント境界一致：案件領域の配下は免除・境界の別物と glob の入れ子は免除しない。
- [x] 編集セッションの指紋キーが `/` 区切り（プラットフォーム非依存）。
