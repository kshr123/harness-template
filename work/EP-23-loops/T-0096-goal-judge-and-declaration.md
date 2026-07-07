---
id: T-0096
kind: task
status: done
title: goal の judge 化（rubric/LLM-judge 採点器）と goal の宣言化（YAML）
created: 2026-07-07
depends_on: [T-0095, T-0092]
verified_by:
  - tests/test_agent_judge.py::test_parse_judge_score_unparseable_is_nan_fail_closed
  - tests/test_agent_judge.py::test_rubric_judge_scores_from_dummy_script_no_network
  - tests/test_agent_judge.py::test_rubric_judge_replays_cassette_fixture_no_network
  - tests/test_agent_judge.py::test_llm_judge_entry_fn_raises_binding_guidance
  - tests/test_agent_judge.py::test_judge_user_text_includes_both_rubric_and_candidate
  - tests/test_agent_goal.py::test_goal_loop_with_llm_judge_continues_until_pass_no_network
  - tests/test_agent_goal.py::test_goal_gate_judge_metric_without_binding_raises_fail_closed
---
# T-0096 goal の judge 化と宣言化（done）

## 狙い
骨組み（T-0095）の goal は exact_match だけ＝答えが一意の場合に限られる。自由文の成功基準
（「手順が 3 段で書かれている」等）を **LLM-judge/rubric 採点器**として `AGENT_METRICS` へ足し、
goal ゲート（`GoalGate`）から**差し替え無しで**使えるようにする（ゲートは metric 名しか見ない設計の証明）。
あわせて goal を**宣言（YAML）**にする（コード内組み立てから卒業＝宣言が正本・DEC-0004 と同型）。

## 設計（fable 詳細設計・確定）
中心の矛盾＝「judge は provider＋rubric が要るが `AGENT_METRICS.fn` は純関数 `(y_true, y_pred) -> float`」を次で解く：
- **rubric は新引数でなく既存 expected（y_true）経路そのもの**＝fn 署名を変えない（`MetricEntry.fn` 純関数契約は温存）。
- **provider だけを束ねる**：`RubricJudge`（frozen・`__call__(y_true, y_pred) -> float`＝純署名と同一）を **goal 宣言の
  読み込み点（`gate_from_goal`）**で綴じる。レジストリには `JudgeEntry(MetricEntry)`（`.fn` は「束ねが要る」案内つき
  ValueError）として `llm_judge` を登録＝カタログ掲載・`passes` の membership・向き解決は既存機構がそのまま効く。
- **`GoalGate` は entry の型だけで分岐**（`judge: RubricJudge | None = None` を 1 つ追加・特定 metric 名のハードコード無し）。
  exact_match だけの goal は差分ゼロで従来どおり＝「ゲートは metric 名しか見ない」の証明。`Goal`/`passes`/`run_agent_to_goal`/
  `loops.py`/`runtime.py` は無変更。
- **判定パースは fail closed**：`parse_judge_score` は `[0,1]` の裸の数値に全文一致だけ許し、それ以外は **NaN**（散文抽出・
  clamp をしない）＝`passes` の NaN 不合格（L-009）に載せて新しい合否機構を作らない。
- **無ネットワーク検証**：dummy judge（台本 `{judge_user_text(rubric,cand): "0.8"}`＝期待は構成から導出）と cassette
  （手書きフィクスチャ・`_reply_from_anthropic` 経由＝実 SDK 形状の契約検査を兼ねる・無いキーは fail closed）。実 judge は
  同じ `RubricJudge` に `AnthropicProvider` を束ねるだけ＝verify 経路外・コード分岐無し（DEC-0015・T-0092 流用）。
- **goal は AgentSpec に埋めず別ファイル `goal.yaml`**（寿命・正本が違う＝実行ごとの宣言／agent は store 版管理・serve 対象。
  1 agent:N goal。judge 節を spec に足すと store roundtrip・serve 全消費者に波及）。`goal_from_mapping` は
  `spec_from_mapping` と同型（extra forbid・未知キー失敗・judge 系⇔`judge:`節の整合・judge 系×純関数系の併用禁止・
  `path` は cassette のときだけ）。
- **新 CLI は足さない**：`agent run` に `--goal <goal.yaml>` を追加するだけ（`--goal-expected` と併用は exit 2・DEC-0016 の
  免除不要）。カタログ・docs/agent.md・skill を同タスクで更新（DEC-0009/0016）。

## 受け入れ基準（detailed）
- `src/harness/agent/judge.py`（新規・stdlib＋agent 内のみ・anthropic 非 import）：`JUDGE_SYSTEM_PROMPT`（コード固定）・
  `judge_user_text`/`judge_messages`（正準テンプレ＝キー導出の 1 か所）・`parse_judge_score`（裸 `[0,1]` 全文一致以外は NaN）・
  `RubricJudge`（frozen・`__call__`）・`make_rubric_judge(*, provider, spec)`。
- `eval.py`：`JudgeEntry(MetricEntry)`（`.fn` は案内つき ValueError）＋ `llm_judge` 登録（`input="label"`・
  `higher_is_better=True`・`tasks=("rubric",)`）。`passes` 無変更。
- `goal.py`：`GoalGate.judge` フィールド＋`_scorer`（entry 型で分岐）・`JudgeDecl`・`goal_from_mapping`・`load_goal`・
  `gate_from_goal`。
- `cli.py`：`agent run --goal`＋`--test` に judge goal スモーク。
- 導線：`uv run agent metrics` に llm_judge が説明つきで載る／docs/agent.md の goal 節に llm_judge 小節／SKILL.md 2 行。
- verify 全成功（無ネットワーク）。

## verified_by（代表テスト）
- `tests/test_agent_judge.py::test_parse_judge_score_unparseable_is_nan_fail_closed`
- `tests/test_agent_judge.py::test_rubric_judge_scores_from_dummy_script_no_network`
- `tests/test_agent_judge.py::test_rubric_judge_replays_cassette_fixture_no_network`
- `tests/test_agent_judge.py::test_llm_judge_entry_fn_raises_binding_guidance`
- `tests/test_agent_goal.py::test_goal_loop_with_llm_judge_continues_until_pass_no_network`
- `tests/test_agent_goal.py::test_goal_gate_judge_metric_without_binding_raises_fail_closed`

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `parse_judge_score` を緩める（散文抽出・clamp・失敗時 0.5/1.0）→ NaN fail closed テストが RED。
2. `GoalGate._scorer` が judge 未束ねを黙って skip/exact_match フォールバック → binding ValueError テストが RED。
3. `judge_user_text` から rubric/candidate を落とす（judge が基準・対象を見ずに採点）→ `test_judge_user_text_includes_both_rubric_and_candidate` が RED（テンプレの意味的契約を直接ピン留め）。

## やらないこと
judge アンサンブル・pairwise/ELO（EP-22 item.md の later のまま）・goal の自動生成・rubric 専用フィールド分離・
GoalGate の複数 judge 対応（name→scorer の Mapping 化）・judge record モード・寛容パース・judge system prompt の宣言化・
`run_agent_eval`（golden set 評価）への judge 束ね口（eval 側は JudgeEntry.fn の ValueError で明示的に閉じる）。
いずれも 2 個目の消費が出てから（DEC-0012）。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。効かせる guard を実際に壊して RED を実測した
（バックアップ→ミューテート→対象テスト RED 確認→バイト同一復元）。
- **MUT1**（`parse_judge_score` の NaN を lenient な 0.5 に）→ `test_parse_judge_score_unparseable_is_nan_fail_closed`＋
  `test_rubric_judge_scores_from_dummy_script_no_network` が RED。fail closed 有効。✓
- **MUT2**（`GoalGate._scorer` の judge 未束ね ValueError を exact_match への黙フォールバックに）→
  `test_goal_gate_judge_metric_without_binding_raises_fail_closed` が RED。束ね強制が有効。✓
- **MUT3c（レビューで検出したギャップ→修正）**：初回実装では `judge_user_text` から `{rubric}` を落とす
  ミューテーション（judge が採点基準に盲目で採点）が**全テスト緑のまま通過**した＝各テストが同じ
  `judge_user_text` で鍵を再計算するため rubric 脱落が鍵空間を潰さず「未台本 candidate→NaN」の assert を
  すり抜ける穴。sonnet に差し戻し `test_judge_user_text_includes_both_rubric_and_candidate`（センチネルで
  rubric/candidate の両在を直接ピン留め）を追加。再ミューテートで確かに RED になることを Opus 側でも実測。✓
  併せて item.md の旧 guard #3（「テンプレ変更→cassette キー不一致で RED」）は事実誤り（cassette テストは
  毎回鍵を再計算し一致する）として訂正済み。
- 過剰対応の釘：cosmetic なテンプレ変更（末尾に説明句を足す等）は RED にしない＝意味を変えず、実 cassette は
  利用者側で fail closed に落ちる。cassette キーの literal 凍結（sha256 べた書き）はコードベース慣行に反する
  ため採らない（fingerprint は独立再計算でピン留めするのが本リポの作法）。
- `uv run verify` 全成功（unit/integration/e2e・ruff・mypy strict・pm 検査）。`uv run agent metrics` に
  `llm_judge` が説明つきで掲載（DEC-0009 の導線を機械で確認）。**APPROVE**。
