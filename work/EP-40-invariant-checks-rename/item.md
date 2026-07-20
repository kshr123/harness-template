---
id: EP-40
kind: epic
status: done
plan: detailed
created: 2026-07-20
closed: 2026-07-20
requirements: []
depends_on: []
---
# EP-40 「プロジェクト管理の検査」を「不変条件の検査」に改名する

`checks.py` が束ねる検査列の名前（識別子 `PM_CHECKS`・型 `PmCheck`・`Profile.pm_checks`・散文
「プロジェクト管理の検査」）が中身とずれていた。この集合が `pm.lint` 主体だった初期は「プロジェクト管理」で
正しかったが、以後 文書↔コード整合・境界・規約・撤回残骸の検査が積み上がり、12件中で管理系は3件だけになった。
残り9件は「リポジトリ自身の規則（不変条件＝invariant＝常に成り立つべき性質）が守られているか」を機械で確かめる、
言語ツール（ruff/mypy/pytest＝普遍的な正しさ）が知らない検査である。名前が実体に追いつかなくなった状態は
この基盤の「撤回」原則が対象にする陳腐化なので、標準用語 invariant を出典に、集合名を1つに揃えた。

## 変更（T-0240）
- 識別子 `PM_CHECKS`→`INVARIANT_CHECKS`、型 `PmCheck`→`InvariantCheck`、`Profile.pm_checks`→`invariant_checks`、
  内部ヘルパ `_pm_checks`→`_run_invariant_checks`（checks.py）／`_invariant_checks`（doc_sync.py）。
- 散文「プロジェクト管理の検査」→「不変条件の検査」（checks.py・doc_sync の HEADING・profiles・core.md・
  AGENTS・README・DoD・verify スキル・checks.toml・ops.md）。初出に「不変条件＝invariant＝常に成り立つべき性質」
  の意味を1文で添える。
- 全プロファイルの `profile.py` の `invariant_checks=` を更新。テスト・配線テスト関数名も揃える。
- 生成物 `docs/core.md` は `uv run doc-sync` で見出し・表を作り直す。

## 触れないもの（履歴記録）
`work/`・`docs/learnings.md`・`docs/archive/` の過去記録は当時の事実なので書き換えない。ただし `verified_by` は
LIVE ポインタ（pm.spec_lint が実在照合する）なので、改名したテストを指す1件（T-0167）だけは追随して更新した。
`src/harness/pm.py`＝作業単位モジュールの「プロジェクト管理」は本来の意味なので残す。

## 経緯
オーナーが「PM って名前が違和感、もっと適切な名称があるのでは」と指摘。中身の分類（管理系3/整合5/構造4）から
「プロジェクト管理」が少数派3件しか説明していないことを確認し、AskUserQuestion で `INVARIANT_CHECKS` を選定。
`uv run verify` 緑を保ち、maker≠checker（別 fable）で差分を確認して完了。
