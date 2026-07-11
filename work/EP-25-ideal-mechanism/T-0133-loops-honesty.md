---
id: T-0133
kind: task
status: done
title: loops の正直化（死んだ語彙の削除と実態への畳み込み）
requirements: [REQ-001]
depends_on: [EP-23]
verified_by:
  - tests/test_agent_goal.py::test_stop_condition_signature_stays_agent_shaped_until_dec
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0133 loops の正直化（歩く骨組み）

## 狙い（なぜ *より理想* になるか）
「core 配置＝一般性が既に見えている」という DEC-0017 の看板を、同じ EP-23 の DEC-0018 が事後に否定した
（ds は fan-out+filter・serve は loop でない・ops は記述のみ＝loops.py を実 import しない）。にもかかわらず
`src/harness/loops.py` は core に残置し、`Trigger` Literal は**消費者ゼロの死んだ語彙**（grep で src/tests に
定義行 1 件のみ）。これは「消費者 1 つで抽象を core に切らない」という自リポの規律（DEC-0012。item.md が
`passes` の core 昇格を拒否した根拠）への**自己矛盾**。消費者が 1 つ（`agent/goal.py`）しかない語彙を消費者の
隣へ畳み、死んだ語彙を削ることで「**配置＝消費の事実**」という自己整合を回復する（縮小でなく、規律の体現）。

## 設計（fable 詳細設計・確定）＝最小のコード変更で自己整合を回復
- **畳み込み**：`StopDecision`・`StopCondition` を `src/harness/agent/goal.py` へ移し、`src/harness/loops.py` を削除。
  `harness.loops` の実消費は goal.py（`from harness import loops`／`StopDecision`）と `tests/test_loops.py`・
  `tests/test_agent_goal.py`（`from harness.loops import StopDecision`）のみ。移設後は goal.py 内の定義を参照する。
- **死んだ語彙の削除**：`Trigger` Literal（loops.py:28）は削除。4 類型（turn/goal/time/event）の分類は
  DEC-0017／EP-23 item.md の**記述**として残す（語彙の正本は docs、コードには実消費だけ置く）。
- **DEC-0020（新規）**：「loops 語彙は agent へ降格・core 再昇格は 2 個目の実 import 消費が出たとき DEC-0012 で
  判断」を記録。過去 DEC（0017/0018）は編集しない（DEC-0012 が DEC-0005 の一点を上書きした先例と同型）。
- **AGENTS.md の追従（doclint が強制＝同タスク必須）**：19–21 行の loops 節を「goal 停止ゲート＝
  `src/harness/agent/goal.py`」を指す形に最小修正（`src/harness/loops.py` のパス参照を消す。残すと doclint の
  死にリンク検査が RED）。
- **テストの追従**：`tests/test_loops.py` を `tests/test_agent_goal.py` へ統合。stdlib-only import テスト
  （軽 import・DEC-0013）はモジュール消滅と共に退場。シグネチャ番人
  `test_stop_condition_signature_stays_agent_shaped_until_dec` は goal.py 版として**存置**（DEC-0018 の番人）。

## 受け入れ基準（detailed）
- `src/harness/loops.py` が存在しない。`Trigger` が src/tests に 1 件も無い。
- `StopDecision`・`StopCondition` が `agent/goal.py` から提供され、`GoalGate`／`run_agent_to_goal` の意味論が不変。
- AGENTS.md 19–21 行が `agent/goal.py` を指す（死にリンク無し）。`docs/decisions/DEC-0020-*.md` が存在。
- 墓標テスト＝`harness.loops` が import できないことを固定（DEC-0020 参照コメント付き）。
- シグネチャ番人テストが goal.py 版として実在し、`check` のシグネチャ拡大で RED。
- `uv run verify` 全成功。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. loops.py を消して AGENTS.md を直さない → `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`
   （実在）と pm 検査が RED（死にリンク）。
2. 墓標テスト新設（`importlib.util.find_spec("harness.loops") is None`・DEC-0020 参照）。
   ミューテーション＝loops.py を復活 → RED（死んだ語彙のゾンビ再導入を止めるラチェット）。
3. `test_stop_condition_signature_stays_agent_shaped_until_dec` を移設存置。
   ミューテーション＝`check` のシグネチャ拡大 → RED（DEC-0018 の番人を維持）。

## 触ってはいけない核
`run_agent_to_goal`・`GoalGate`・judge・`eval.passes`（fail-closed）・CLI・exit-1 の意味論。
`tests/test_agent_goal.py` の**アサーションは 1 文字も変えない**（import 行の変更のみ許す）。

## verified_by
- `tests/test_agent_goal.py`（既存・全通過のまま＋墓標/番人を移設）
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`（既存＝AGENTS の死にリンク検知）

## やらないこと
goal ゲート・judge・CLI・exit-1 の意味論変更／4 類型分類の docs からの削除（記述として残す）／過去 DEC の
改変／`loops.py` を空 re-export で残すこと（死んだ語彙を残さない＝畳み込みの目的に反する）。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。効かせる guard を実際に壊して RED を実測（バックアップ→
ミューテート→対象テスト RED→バイト同一復元・working copy 健全を確認）。
- **G-sig**（`StopCondition.check` に kw-only 引数を追加）→ `test_stop_condition_signature_stays_agent_shaped_until_dec`
  が RED。DEC-0018 の番人が移設先（goal.py 版）でも生きている。✓
- **G-tomb**（`src/harness/loops.py` をゾンビ復活）→ `test_harness_loops_module_does_not_exist` が RED。死んだ語彙の
  再導入を止めるラチェットが効く。✓
- **G-deadlink**（AGENTS.md を削除済み `src/harness/loops.py` へ戻す）→ `test_doclint.py::test_real_repo_docs_have_no_dead_links`
  が RED。畳み込みに伴うパス追従を機械が強制。✓
- **実装者の good catch と判断**：(1) DEC-0018 本文が `tests/test_loops.py` を自己参照し死にリンク化するため、決定内容
  （状況/選択肢/理由/status）は一切触れず番人テストのパス参照 1 行だけを `tests/test_agent_goal.py` に更新＋T-0133/DEC-0020
  への前方参照を注記（DEC-0012 が DEC-0005 を注記で改定した先例と同型＝「過去 DEC の決定は改変しない」を守った保守更新と判定・
  容認）。(2) done タスク T-0099 の `verified_by` が旧テストを指すため移設先へ更新、退場した `test_loops_module_import_is_stdlib_only`
  は対象モジュール消滅で代替不能である旨を prose に明記（黙って落とさない）。(3) `docs/agent.md` の loops 節も指し先を追従
  （4 類型分類の記述は温存）。いずれも「正直化」の趣旨に沿う。
- **意味論の不変を確認**：`GoalGate.check`・`run_agent_to_goal`・judge・`eval.passes`(fail-closed)・CLI・exit-1 は型参照の
  更新（`loops.StopDecision`→`StopDecision`）のみで挙動不変。`test_agent_goal.py` の既存アサーションは無変更（import 行のみ）。
  他プロファイルへの import 逆流なし（DEC-0004 維持）。`Trigger` は src/tests から消滅（消費者ゼロの死んだ語彙を除去）。
- `uv run verify` 全成功。**APPROVE**。
