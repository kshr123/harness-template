---
id: T-0138
kind: task
status: done
title: レビューの深さを差分のリスクに比例させる（規約明文化・機械検査にしない）
requirements: [REQ-001]
depends_on: [T-0134]
verified_by:
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0138 レビューのリスク比例化（改訂＝規約明文化・機械検査にしない）

## 狙い（なぜ *より理想* になるか）
EP-23 の実測（独立ミューテーションレビューが genuine な欠陥を捕まえたのは「新 guard を導入したタスク」に集中し、
docs/写像タスクでの捕獲は 0）に基づき、レビューの**深さ**を差分の内容で決める。独立性（作る側と確かめる側を分ける）
は全 tier で不変・深さだけ比例させる＝最適配分。**当初設計は「done はレビュー節必須」の pm 検査＋`review_scope` 純関数を
足す機械化だったが、owner 決定（2026-07-07・EP-24 rollback 整合）で改訂**：「レビュー節が在るか」の pm 検査は撤去された
「lede 必須」検査と同型の**文書構造の機械化**なので新設しない。判定基準を **review スキル＋DoD に〈私への規約〉として
明文化**する（機械化の射程は構造/コード不変条件だけ・文書/プロセス規律は規約）。

## 設計（確定・改訂後）
- **review スキル（`.claude/skills/review/SKILL.md`）に「レビューの深さは差分のリスクに比例」節を追加**：
  - 独立性は全 tier 不変。深さだけ差分が触れるパスで決める（判定は事実＝恣意でない）。
  - **full**：`src/`・`tests/`・`templates/`・`.pre-commit-config.yaml`・`pyproject.toml` に触れる → 別モデルで独立レビュー
    ＋効かせる guard を実際に壊して対象テストが RED になることを実測（ミューテーション）。
  - **light**：`docs/`・`work/` のみ → 差分レビュー＋verified_by の実在確認＋`uv run verify` 緑（ミューテーション不要）。
  - 根拠（EP-23 実測）と「これは規約であって pm 検査にしない」旨を 1 文。
- **DoD（`docs/DoD.md`）に 1 行**：独立確認の項に「レビューの深さは差分のリスクに比例（full/light・判定基準は review スキル）」。
- **新 pm 検査・`review_scope` 純関数・`Issue`/spec_lint 拡張は足さない**（当初設計から撤回）。

## 受け入れ基準（detailed）
- review スキルに tiering 節（full/light の判定基準・独立性は全 tier 不変・EP-23 根拠・「規約であって機械検査にしない」）。
- DoD に 1 行の導線。
- 参照するパス（`.claude/skills/`・`docs/`）が実在（doclint 緑）。`uv run verify` 全成功。
- **`src/harness/**`・pm 検査に差分なし**（機械化を足さない改訂の証明）。

## verified_by（規約タスク＝機械検査を新設しないので既存の参照整合で束ねる）
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`（review スキル・DoD の参照が実在＝編集が壊れていない）。
（**tiering の規則内容そのものは機械検査しない＝review观点**。owner 決定：文書/プロセス規律は規約であって pm 検査にしない。
この verified_by は「編集が docs 参照を壊していない」ことの機械的裏づけであり、規則の正しさは独立レビューが確かめる。）

## 効かせる guard
- 本タスクは機械検査を足さない（規約明文化）ので「効かせる guard（ミューテーション）」は無い＝docs-only の light tier
  （＝このタスクが定義する規則を自分自身に適用：docs のみ→light レビュー）。参照整合は doclint が守る。

## 触ってはいけない核
review スキルの「重大な問題はブロック」意味論・DoD の独立確認要件（**深さ**を比例化するので**独立性**は全 tier 必須のまま）・
verify-gate・pm 検査（足さない）。

## やらないこと
`review_scope` 純関数・「done はレビュー節必須」の pm/spec_lint 検査・`Issue` 拡張（当初設計から撤回＝owner 決定）／
文書規律の機械化／独立性の緩和（比例化するのは深さだけ）。

## 独立レビュー（sonnet・別モデル・light tier・作る側と確かめる側を分ける・問題なし）
maker＝Opus（本タスクの doc 編集）・checker＝sonnet（別モデル）。docs-only なので本タスク自身が定義する light tier
（差分レビュー＋verified_by 実在＋verify 緑・ミューテーション不要）を自己適用。fable が利用上限で落ちたため sonnet で実施
（どちらも Opus とは別モデル＝maker≠checker 成立）。
- review スキルの新節は「独立性は全 tier で不変・深さだけ差分のリスクに比例（full=src/tests/templates→ミューテーション／
  light=docs/work のみ）」を正しく述べ、**独立性を緩めていない**。DoD の 1 行が整合。✓
- 新 pm 検査・`review_scope` 純関数を足していない（`git diff --stat -- src/harness` 空）＝owner 決定（文書/プロセス規律は
  規約・機械化しない）と整合。✓
- 判定：**問題なし**。`uv run verify` 全成功（統合ツリー）。
