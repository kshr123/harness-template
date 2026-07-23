---
id: T-0250
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 1
requirements: []
depends_on: [T-0249]
verified_by:
  - tests/test_deliver_overlay.py::test_the_shipped_template_loads_as_is
  - tests/test_coverage_lint.py::test_real_repo_all_cli_commands_are_reachable
  - tests/test_profile_doc_lint.py::test_real_repo_profiles_are_reachable_from_index
---
# T-0250 使う人が元コードを読まずに辿り着ける状態にする

## 作ったもの

- `.claude/skills/wbs/SKILL.md` … 場面ごとの手順（提案・キックオフで合意する／定例で報告する／
  遅延・スコープ変更で引き直す／最終報告）。困ったときの指摘の読み方（拒否は「空の工程表・嘘の由来を
  渡さないための拒否」なので、黙らせずに直す）も書いた。
- `.harness/templates/wbs.yaml` … 案件を始めるときの上書きの雛形。コピーしただけの状態で読める
  （初手で検査に落ちない）ことをテストで固定した。
- `docs/deliver.md` から手順と雛形へのリンク。`AGENTS.md` に「顧客向けの WBS・工程表」の項を追加
  （日程の正本は `work/` ひとつで、WBS 側に第 2 の台帳を作らない、という決まりごとの本体）。

## 受け入れ基準

- [x] 新しいコマンドがすべてスキルか正本 docs から辿れるか（導線の検査に失敗しないか）。
- [x] 雛形をそのまま置いた状態で読めるか。
- [x] プロファイルの正本が doc 索引から辿れるか。
