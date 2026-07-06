---
id: T-0088
kind: task
status: todo
title: 導線カバレッジ検査（coverage_lint＝全 CLI コマンドがスキル/正本 docs から到達可能）
created: 2026-07-06
depends_on: [T-0069]
---
# T-0088 導線カバレッジ検査（coverage_lint）

## 背景（DEC-0009 の第 3 要件を機械化する）
「部品は入口まで作って完了」（DEC-0009）の DoD 3 要件のうち、①レジストリ登録②docstring は機械検査があるが、
③「スキル/雛形からの導線」は未機械化＝書き忘れても verify は緑。実測で `data selectors`/`data tuners` 等がスキル言及 0。
doclint は dead link（参照先が在るか）だけ＝一方向。逆向き（能力が増えたのに導線が無い＝missing link）を止める。

## 受け入れ基準（core・stdlib のみ・profile を import しない）
- **新モジュール `src/harness/coverage_lint.py`**：`run_checks(root)->list[pm.Problem]`（PmCheck 型）。
  - `src/harness/**/cli.py` を **ast で解析**（import しない＝doclint と同じテキスト/AST 作法でプロファイル境界を壊さない）。
    各関数の装飾子 `@<app>.command("name")` を全抽出。app 変数から接頭辞を導出（`data_app`→`data`・`issue_app`→`issue`・
    `serve_app`→`serve`＝`_app` を剥がす）。トークン＝`f"{prefix} {name}"`（`name==prefix` のときは `prefix` 単体＝serve）。
  - 探索コーパス＝`.claude/skills/**/*.md` ＋ `AGENTS.md` ＋ `README.md` ＋ `docs/*.md`（非再帰）。各トークンが 1 回以上
    現れれば到達可能。現れない＝**error**（メッセージは「どの cli.py のどのコマンドが、どの導線に無いか」を名指し）。
  - **免除リスト** `_EXEMPT: dict[str,str]`（トークン→理由）：真に導線不要な内部コマンド（例 `data lint`＝schema 検査の
    内部入口・verify から呼ぶ）だけを、**理由コメント必須**で載せる（サイレントな見逃しを防ぐ＝過検出より取りこぼしを許容の逆で、
    ここは missing を error にするので免除を明示的に）。
- **配線**：`src/harness/checks.py` の PM_CHECKS（プロファイル非依存の検査列）に `coverage_lint.run_checks` を追加。
- **既存欠落の解消**：検査を緑にするため、実測で欠けているコマンド（`data selectors`/`data tuners` ほか）を**既存スキル**
  （features/experiment/eda 等）に 1〜2 行ずつ足す（新スキルは作らない＝method E 節の 3 条件に照らし追記で十分）。導線不要と
  判断したものだけ `_EXEMPT` に理由つきで。
- **規約昇格（DEC-0012＝即）**：`AGENTS.md` に 1 行＋強制点の括弧書き（「新しい CLI コマンドはスキル/正本 docs への導線が必須
  ＝coverage_lint が検査」）。`docs/learnings.md` に観察を 1 件（missing link は一方向 doclint では捕まらない）→ 即 DEC を起こす。

## 触ってよいファイル
`src/harness/coverage_lint.py`（新規）・`src/harness/checks.py`（PM_CHECKS 追加）・`.claude/skills/**`（導線の追記のみ）・
`AGENTS.md`（1 行）・`docs/learnings.md`（1 件）・`docs/decisions/DEC-00xx-*.md`（新規）＋`tests/test_coverage_lint.py`（新規）。
`doclint.py`・`cli.py` 群のコマンド定義は**変更しない**（読むだけ）。

## 検査（テスト先書き・構成から導く）
- 一時プロジェクトに小さな cli.py（`@data_app.command("_orphan")` を含む）＋スキルを置き、`_orphan` が error になる（ast 抽出と
  未到達判定が効く）。同じ名前をスキルに 1 行足すと消える（到達判定が効く）。`_EXEMPT` に載せると消える（免除が効く）。
- 自リポ（REPO_ROOT）に対して `run_checks` が **0 件**（実データを緑化した後の回帰の番人＝以後の導線忘れを止める）。
- 変異：`checks.py` から coverage_lint を外すと、わざと導線を消したコマンドが検出されなくなる（配線が効く）ことを確認。
- `uv run verify` 全体緑。

## 独立レビュー（maker≠checker・差分のみ・実測）
（レビュー後に記入）
