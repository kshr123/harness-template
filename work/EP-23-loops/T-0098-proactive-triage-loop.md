---
id: T-0098
kind: task
status: done
title: proactive 閉ループの後半円（issue→修正→検証緑で close・maker≠checker を保つ）
created: 2026-07-07
depends_on: [T-0097]
verified_by:
  - tests/test_agent_monitor.py::test_filed_issue_has_exit_condition_section
  - tests/test_agent_monitor.py::test_cli_agent_monitor_file_issue_refiles_after_resolved
  - tests/test_agent_monitor.py::test_cli_agent_monitor_file_issue_is_idempotent
  - tests/test_issues.py::test_resolved_requires_promoted_target_done
  - tests/test_issues.py::test_done_target_but_issue_still_open_is_error
---
# T-0098 proactive triage 閉ループ（done）

## 狙い
blog の proactive（schedule＋goal の合成。各タスクは goal 達成で退場・routine は無効化まで継続）を閉じる。
前半円（監視→冪等起票）は `agent monitor --file-issue` で実装済み。後半円＝**起票された issue を goal として
拾い（例：「`uv run verify` 緑かつ non_end_turn_rate が安定帯」）、修正し、達成したら close して退場**する
流れを loops 語彙で設計する。

## 設計（fable 詳細設計・確定）＝コード最小・自動化ゼロ追加
**核の判断：後半円の関門は既存構造が全部持っている。** `issues.run_checks` の不変条件＝**resolved ⟺ `promoted_to` タスクが done
⟺（done↔verified_by 結びつけ＋`uv run verify` 緑）**＝「検証緑で close」は新設不要。さらに `test_resolved_same_drift_refiles`
が示すとおり **resolved 後も帯が悪ければ次の monitor 実行が同タイトルで再起票**＝「修正が効いたか」の最終判定者は前半円（monitor）
自身＝**前半円が後半円の checker を兼ねる**。T-0098 が足すのは「退場条件を人が読める 1 節」「フローと承認点の docs 正本化」
「関門を守るテストの明示的な束ね」だけ。
- **issue→goal は方式 (c) 固定 goal を採る**（(a) `Issue` モデルに `goal` 追加＝**却下**：issues は core・goal は agent＝DEC-0004 境界
  違反＋`extra="forbid"` 変更が全消費者に波及＋機械可読 goal は自律 auto-fix への滑り台。(b) body に goal.yaml 断片＝却下：同じ滑り台
  か死んだ規約）。monitor issue の退場条件は常に固定 2 条件：**(i) promoted_to タスクが done（run_checks が機械強制）・(ii) 次回 monitor で
  帯が安定＝再起票されない（既存テストが機械強制）**。両方とも既存機構が検査＝宣言の重複を作らない。
- **唯一のコード変更**：`agent/cli.py::_agent_monitor` の `--file-issue` body（cli.py:390 付近）に `## 退場条件（goal）` 節（固定文）を
  追加＝人が triage で読む退場条件の宣言（機械はこれを読まない・検査は run_checks と再起票が担う）。`Issue` モデル・`run_checks`・
  monitor の exit code は**無変更**。
- **maker≠checker の approval フロー**：front（monitor 冪等起票・exit 0）→ [承認点 1] 人の triage（`uv run issue list --open` で拾い
  promoted_to 記入・自動化しない）→ maker（修正タスク実装）→ checker（review スキル＝独立レビュー＋verify 緑）→ [承認点 2] 人が
  タスク done＋issue resolved を同一コミットで確定（片方だけは run_checks が両向き error）→ 退場。**自律 auto-fix を構造で禁止**：
  ハーネスに「issue を読んで修正を生成・適用・merge する」経路を置かない・`issue promote`/`issue close` の CLI を**意図的に作らない**
  （状態遷移は frontmatter 手編集＝人の行為が唯一の口）・monitor は exit 0 のまま（門番化しない）。
- **新 CLI は足さない**（既存 `agent monitor --file-issue`＋`uv run issue list/check/new`＋通常のタスク運用で全段が回る）。
- **導線**：docs/agent.md の time-based 節直後に「proactive 閉ループ（前半円＋後半円）」小節（フロー・承認点・**やらないこと**）＝停止は
  T-0097 の stop 規律に合流（参照・重複記述しない）。item.md 写像表の proactive 行を実名で更新。`.claude/skills/session/SKILL.md` に
  1 行（着手前に `uv run issue list --open` で open 課題を確認・promote/wontfix は人が決める）。`templates/schedule/README.md` に
  後半円への参照 1 行。

## 受け入れ基準（detailed）
- `agent monitor --file-issue` の起票 body に `## 退場条件（goal）` 節（promoted_to done＋再起票なしの 2 条件が読める固定文）が入る。
- 冪等・exit 0・resolved 後の再起票の既存挙動が無変更。`Issue` モデル・`run_checks`・monitor exit code に変更なし。
- docs/agent.md の proactive 小節・item.md 写像表・session スキル・schedule README の導線が同タスクで更新。
- `uv run verify` 全成功。

## verified_by（代表テスト）
着手時に確認：`tests/test_monitor_file_issue.py` は `data monitor --file-issue`（ds プロファイル・T-0115）の
テストで、`agent monitor --file-issue`（本タスクの対象＝`agent/cli.py::_agent_monitor`）とは別ファイル。
下記は実名を `tests/test_agent_monitor.py` に合わせたもの（`test_cli_agent_monitor_file_issue_refiles_after_resolved`
は既存不変条件の代わりが無かったため最小の同等テストとして新規追加）。
- `tests/test_agent_monitor.py::test_filed_issue_has_exit_condition_section`（新規＝退場条件節の存在）
- `tests/test_issues.py::test_resolved_requires_promoted_target_done`（既存＝検証緑で close の機械強制）
- `tests/test_issues.py::test_done_target_but_issue_still_open_is_error`（既存＝閉じ忘れの逆向き強制）
- `tests/test_agent_monitor.py::test_cli_agent_monitor_file_issue_is_idempotent`（既存＝前半円の冪等・非門番）
- `tests/test_agent_monitor.py::test_cli_agent_monitor_file_issue_refiles_after_resolved`（新規＝後半円の goal
  未達検知・close の冪等。ds 側 `test_monitor_file_issue.py::test_resolved_same_drift_refiles` と同じ境界を
  agent monitor 側でも守る）

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `run_checks` の「resolved だが対応先が done でない」error を削る → resolved⟺done のテストが RED（verify 緑ゲートの心臓）。
2. 起票 body から退場条件節を削る → `test_filed_issue_has_exit_condition_section` が RED（goal 宣言の欠落を検知）。
3. 再起票判定の `state is open` フィルタを全状態に広げる（resolved が再起票を塞ぐ変異）→
   `test_cli_agent_monitor_file_issue_refiles_after_resolved` が RED（後半円の checker が死ぬ変異を検知）。

## やらないこと
承認無しの自動 merge・自律 auto-fix（issue を機械が読んで修正を生成・適用する経路をハーネスに置かない）・監視を門番化すること
（monitor は exit 0 のまま＝起票は副作用、の既存規律を壊さない）・`issue promote`/`issue close` CLI の新設・`Issue` モデル拡張・
goal.yaml の issue 流用・issue 用 lint の新設・新 CLI。可変退場条件の実需が出たら DEC で再判断（DEC-0012）。
`work/EP-20*`・`work/EP-21*`・`src/harness/ops/**` には触れない（本設計はその必要が無い）。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。効かせる guard を実際に壊して RED を実測（バックアップ→ミューテート→
対象テスト RED→バイト同一復元）。
- **G1**（`issues.run_checks` の「resolved だが対応先が done でない」error を削除）→ `test_resolved_requires_promoted_target_done`
  が RED。**検証緑で close** の関門（後半円の心臓）が生きている。✓
- **G2**（起票 body から `## 退場条件（goal）` 節を削除）→ `test_filed_issue_has_exit_condition_section` が RED。退場条件宣言の
  欠落を検知。✓
- **G3**（再起票の冪等フィルタ `state is open` を全状態に広げる＝resolved が再起票を塞ぐ変異）→
  `test_cli_agent_monitor_file_issue_refiles_after_resolved` が RED。**前半円が後半円の checker を兼ねる**（帯が悪ければ再起票＝
  goal 未達の機械判定）が生きている。✓
- **実装者の good catch**：設計が verified_by に指した `tests/test_monitor_file_issue.py` は実は `data monitor`（ds/T-0115）の
  テストで、本タスク対象 `agent monitor`（`agent/cli.py::_agent_monitor`）とは別。sonnet が正しい `tests/test_agent_monitor.py` に
  置き換え＋不足していた再起票不変条件テストを最小追加した（空振り verified_by を防いだ）。Opus 側で 5 テストの実在を grep で確認。
- **自動化ゼロ追加の確認**：`git diff` の本番コード変更は cli.py の body に節を 1 つ足すのみ（+6 行）。新 CLI・`issue promote/close`・
  issue 状態の自動遷移・自律 fix 経路は一切足していない（唯一の `IssueState.resolved` 参照はテストの前提 assert）。docs の
  proactive 小節は承認点 1・2（人）と「自律 auto-fix を作らない／承認無し merge を作らない／門番化しない」を明記。maker≠checker の
  approval 構造が壊れていない。✓
- `uv run verify` 全成功。**APPROVE**。
