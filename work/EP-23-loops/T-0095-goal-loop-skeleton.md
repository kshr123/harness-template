---
id: T-0095
kind: task
status: done
title: loops 歩く骨組み（core 語彙＋goal-based 停止ゲート＝評価器が合格と言うまで続行・無ネットワーク）
created: 2026-07-07
depends_on: [T-0091]
verified_by: [tests/test_agent_goal.py::test_goal_loop_continues_until_gate_passes_no_network]
---
# T-0095 loops 歩く骨組み（core の語彙＋agent の goal-based ループ）

## 狙い（端まで通る最小＝method.md A 節）
入力（AgentSpec＋**Goal 宣言**）→処理（`run_agent` の往復）→**停止判定（評価器ゲート＝`AGENT_METRICS`＋
`eval.passes`）**→未達なら続行注入→出力（GoalRun）→検証（`--test` スモーク＝`uv run verify` 接続）を 1 本通す。
blog の 4 類型のうち**真に新規なのは goal-based だけ**：turn-based は `run_agent` が既にその形
（end_turn 停止＋max_turns backstop）で、本タスクは「end_turn で止まろうとするたび goal を検査し、未達なら
続けさせる」1 点を足す。**核の制約＝テスト中にネットワークを一切叩かない**（dummy の台本＋`_cut_network`・DEC-0015）。

## 設計判断（根拠つき）
- **語彙は core・実装は agent**：`harness/loops.py` は stdlib のみの宣言（DEC-0013）。ds/ops でも使う一般性が
  見えているが（item.md 写像表）、プロファイル同士は import 不可（DEC-0004）＝共有は core 経由のみ。
  採点器・合否（`AGENT_METRICS`/`passes`）は agent 資産のまま core へ引き上げない（消費者 1 つ・DEC-0012）。
- **`run_agent` を丸ごと再利用**し、goal ループはその外側に巻く（往復ループの再実装をしない＝DEC-0006 の思想）。
  続きの会話に「続けろ」を注入するため、`run_agent` に後方互換の続行口 `prior_messages` を 1 つ足すだけ。
- **ゲートは fail closed**：合否は既存 `eval.passes`（NaN・欠けは不合格・未登録名は ValueError）をそのまま使う。
  「止めさせない」の backstop は `max_cycles`（黙って無限ループしない＝runtime の max_turns と同じ規律）。
- **新 CLI コマンドは足さない**：`agent run` にオプションを足す（コマンド面を増やさない＝coverage_lint の対象
  不変・DEC-0016。導線は docs/agent.md とスキルに書く＝下記）。

## 受け入れ基準
### `src/harness/loops.py`（新規・core・stdlib のみ・DEC-0013）
- `Trigger = Literal["turn", "goal", "time", "event"]`：4 類型の語彙。docstring に各類型と既存部品の対応を
  1 行ずつ（turn=`run_agent`・goal=本タスク・time=schedule 雛形 T-0097・event=monitor `--file-issue` T-0098）。
- `StopDecision`（`@dataclass(frozen=True, kw_only=True)`）：`stop: bool`・`reason: str`（"goal_met" 等の
  人が読む文字列。enum にしない＝消費は表示と来歴のみ・追加を型変更にしない）。
- `StopCondition` Protocol：`def check(self, *, output: str, iteration: int) -> StopDecision`。骨組みでは
  テキスト出力への門だけ（引数の一般化は 2 個目の消費＝ds sweep が要ったとき DEC-0012 で判断、と docstring に明記）。
- `LoopSpec` は**作らない**（宣言の正本は AgentSpec/Goal 側＝item.md の設計判断。docstring に 1 行残す）。
- import は stdlib（dataclasses/typing）のみ。プロファイルを import しない（DEC-0004）。

### `src/harness/agent/goal.py`（新規・軽 import＝stdlib＋agent 内＋harness.loops のみ）
- `Goal`（`@dataclass(frozen=True, kw_only=True)`）：`expected: str`／`metrics: tuple[str, ...] = ("exact_match",)`／
  `thresholds: Mapping[str, float]`。docstring：goal は**人が宣言する成功基準**（自動生成しない）。
- `GoalGate`（frozen dataclass・`loops.StopCondition` を実装）：`check(*, output, iteration)` が
  `{name: AGENT_METRICS.resolve(name).fn(goal.expected, output)}` を採点し `eval.passes(scores, thresholds)` で
  合否（向き・fail closed は既存規約のまま）。stop 時 `reason="goal_met"`・未達時はスコア入りの
  `"goal_not_met: exact_match=0.000"` 形式（来歴で人が読める）。未登録 metric は `resolve` の候補一覧つき
  ValueError（既存挙動の流用＝新しいエラー経路を作らない）。
- `GoalRun`（frozen）：`final: AgentRun`／`cycles: int`／`stop_reason: str`（`"goal_met" | "max_cycles"`）／
  `gate_reasons: tuple[str, ...]`（各サイクルの判定＝来歴）。
- `run_agent_to_goal(spec, user_input, *, provider, gate: StopCondition, continue_prompt: str = 既定文,
  seed: int, max_cycles: int = 4, max_turns: int | None = None) -> GoalRun`：
  1. `run_agent(spec, user_input, provider=…, seed=…, max_turns=…)` で 1 サイクル実行。
  2. `gate.check(output=run.output, iteration=サイクル番号)`。stop なら `stop_reason="goal_met"` で返す。
  3. 未達なら `run_agent(spec, continue_prompt, prior_messages=run.messages, …)` で続行（会話履歴を保つ）。
  4. `max_cycles` 到達で `stop_reason="max_cycles"` で必ず止まる（1 未満は ValueError＝runtime と同文言の規律）。
  純関数（ネットワーク・ファイル I/O なし）。`gate` は Protocol で受ける（judge 化 T-0096 の差し替え口）。
  既定 `continue_prompt` は「まだ成功基準を満たしていない。前の応答を見直して続けること」相当の定数
  （policy＝続行の方針はゲートでなくループ側の引数＝trigger×stop×policy の分離を写す）。

### `src/harness/agent/runtime.py`（続行口の追加のみ・後方互換）
- `run_agent` に keyword-only `prior_messages: Sequence[Mapping[str, Any]] = ()` を追加し、
  `messages = [*prior_messages, *build_messages(user_input)]` で開始する。**省略時の挙動・既存テスト・
  `AGENT_LOG_FIELDS` 契約・app.py は不変**（触るのはこの 1 引数だけ。ログ契約のキーは増やさない）。

### `src/harness/agent/cli.py`（`agent run` の拡張・新コマンド無し）
- `--goal-expected <text>`（指定時のみ goal 経路）・`--goal-threshold 名=値`（繰り返し可・`_parse_thresholds`
  再利用・省略時 `exact_match=1.0`）・`--max-cycles`（既定 4）。goal 経路は `run_agent_to_goal` を呼び、
  stdout は最終応答のみ・来歴（`cycles`・`stop_reason`・`gate_reasons`）は stderr（既存 run と同じ分離）。
  goal 未達（max_cycles 打ち切り）は exit 1（**評価器が合格と言うまで完了にしない**を exit code に写す。
  monitor の「門番にしない」とは役割が違う＝これは実行の合否そのもの）。
- `--test` に goal ループのスモークを追加：台本 dummy（1 サイクル目は不一致・continue_prompt 鍵で正解）で
  `cycles==2`・`goal_met` を確認（期待は台本の構成から導出）。失敗なら exit 1（verify に接続）。

### 導線・規約昇格（DEC-0016 / DEC-0012）
- `docs/agent.md`：「loops（trigger×stop×policy）」節＝4 類型の語彙・`run_agent`＝turn-based・
  `agent monitor --file-issue`＝proactive の前半円という位置づけ・goal 経路の CLI 例（`--goal-expected` ほか）。
- `.claude/skills/agent/SKILL.md`：goal ループ 1〜2 行（いつ使うか＝「答えの成功基準を宣言できるとき」）。
- `docs/decisions/DEC-0017-loops-operating-model.md` を accepted 化（本エピックで草案済み）。
- `AGENTS.md` に loops 語彙の 1 行（agent プロファイル節の隣・「goal-based の停止は評価器ゲート」）＝
  **実装フェーズで要更新**（設計では触らない）。`docs/learnings.md` に 1 件（end_turn は「完了した気になった」
  であって「基準を満たした」ではない＝評価器ゲートで機械化した、の観察）。

## 触ってよいファイル
`src/harness/loops.py`（新規）・`src/harness/agent/goal.py`（新規）・`src/harness/agent/runtime.py`
（`prior_messages` 追加のみ）・`src/harness/agent/cli.py`（`agent run` 拡張＋`--test` 追記のみ）・
`docs/agent.md`・`.claude/skills/agent/SKILL.md`・`AGENTS.md`（1 行）・`docs/learnings.md`・
`docs/decisions/DEC-0017-*.md`（accepted 化）・`tests/{test_loops.py,test_agent_goal.py}`（新規）＋
`tests/test_agent_e2e.py`（`--test` スモークの期待追記）。**`ds/**`・`serve/**`・`src/harness/ops/**`・
`docs/ops.md`・`AGENT_LOG_FIELDS` 契約・`app.py` は変更しない。**

## 検査（テスト先書き・構成から導く期待値・マーカー必須・無ネットワーク）
- `tests/test_agent_goal.py::test_goal_loop_continues_until_gate_passes_no_network`（**integration**）：
  台本 dummy `replies={"問い": "下書き", "<continue_prompt>": "正解"}`＋`Goal(expected="正解",
  thresholds={"exact_match": 1.0})` → `cycles==2`・`stop_reason=="goal_met"`・`final.output=="正解"`・
  `gate_reasons` が（未達, goal_met）の並び。**期待はすべて台本の構成から導出**（金メッキ禁止）。
  `_cut_network`（socket 差し替え＝test_agent_e2e.py の既存パターン）でネットワーク 0 を断つ。
- max_cycles backstop（**integration**）：台本が常に不一致 → `max_cycles=3` で `cycles==3`・
  `stop_reason=="max_cycles"`（黙って回り続けない）。`max_cycles=0` は ValueError。
- `GoalGate` 単体（**unit**）：一致で `stop=True`／`reason=="goal_met"`・不一致で `stop=False` かつ reason に
  スコアが載る。未登録 metric 名は候補一覧つき ValueError。thresholds に未登録名＝`passes` の ValueError
  （fail closed の既存挙動が goal 経由でも生きることの確認）。
- `prior_messages` 続行口（**unit**）：`run_agent(…, prior_messages=前回の messages)` で provider が受ける
  messages が `[*prior, 新 user]` になる（dummy の台本鍵＝最後の user テキストで観測）。省略時は従来どおり
  （既存の runtime テストが無修正で緑＝後方互換の証明）。
- `tests/test_loops.py`（**unit**）：`GoalGate` が `StopCondition` を満たす（mypy strict が正本・実行時は
  check の返り値が StopDecision であることを確認）。`harness.loops` の import が stdlib のみ（軽 import＝
  既存 subprocess テストの作法で確認）。
- tool 往復×goal の合成（**integration**）：サイクル 1 が calculator 往復（`tool_use`→`tool_result`）の末に
  不一致 → サイクル 2 で goal_met（`run_agent` 丸ごと再利用の証明。台本は `--test` の calculator 例を流用し
  期待 turns/cycles は台本から導出）。
- e2e：`agent run --test` が goal スモーク込みで緑（既存 `test_agent_eval_smoke_no_network` の経路）。
- coverage_lint 緑（新コマンド無し＝`agent run` は到達済み）・`uv run verify` 全体緑。
- done にする際 `verified_by` へ `tests/test_agent_goal.py::test_goal_loop_continues_until_gate_passes_no_network`
  を記入（frontmatter は実装完了時に更新＝空の done は検査で落ちる）。

## この骨組みでやらないこと（soon/later・理由つき）
- **LLM-judge の goal・goal の YAML 宣言**：T-0096（採点器の拡張と宣言の置き場は judge の形が決まってから）。
- **time-based／proactive の実装**：T-0097/T-0098（本タスクは語彙と goal ゲートだけ）。
- **serve `/invoke` への goal 適用**：リクエスト駆動＝loop でない（item.md の「やらないこと」）。
- **`LoopSpec`・StopCondition の一般化・core への passes 引き上げ**：2〜3 個目の消費で DEC-0012 判断。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
実装は sonnet。詳細設計は fable。レビューは別文脈・別モデル（Opus）が差分のみを実測・変異で確認（**APPROVE**）。
- **ゲートの fail closed＝変異で確認**：`goal.py` の `if passes(scores, dict(self.goal.thresholds)):` を `if True:`
  に潰す → `test_agent_goal.py` の 5 件（不一致報告・未登録閾値の fail closed・tool 往復×goal 合成ほか）が RED
  ＝ゲートが本当に `AGENT_METRICS`＋`eval.passes` を門にしていることを実測（新しい合否機構を作っていない）。
- **max_cycles backstop＝変異で確認**：`if cycle >= max_cycles:` を `if cycle > max_cycles:` に変異 →
  `test_goal_loop_stops_at_max_cycles_backstop` が RED（cycles==4≠3）＝黙って回り続けない打ち切りが load-bearing。
- **会話履歴のサイクル間引き継ぎ＝変異で欠落を発見→修正**：`run_agent_to_goal` の `prior_messages = run.messages`
  を `prior_messages = ()` に潰しても当初 10 件が全緑＝**goal ループの中核「履歴を保って続行」に回帰テストが無い**
  ことをレビューが検出。実装者（sonnet）へ差し戻し、`test_goal_loop_carries_conversation_across_cycles_no_network`
  （integration・無ネットワーク）を追加。再変異で当該テストのみ RED・他 10 件は緑を実測＝欠落を閉じたことを確認。
- **後方互換（`prior_messages` 省略時）＝実測**：既存 runtime テスト無修正で緑・`test_prior_messages_default_matches_
  existing_behavior_no_network` が省略時＝`build_messages(user_input)` 始まりを直接ピン留め（返り値契約 `AgentRun`
  は不変・`.messages` は既存フィールドの再利用）。
- **無ネットワーク＝担保**：goal テストは全て `_cut_network`（socket 差し替え）＋dummy 台本で回る（DEC-0015）。
- **core `loops.py` の軽さ・境界＝subprocess 実測**：`test_loops_module_import_is_stdlib_only` が別プロセスで
  numpy/polars/sklearn/anthropic/fastapi 等の未ロードを確認（DEC-0013）。プロファイルを import しない（DEC-0004）。
- **役割分離＝文書一致**：goal 未達（max_cycles 打ち切り）は `agent run` が exit 1（評価器が合格と言うまで完了に
  しない）・monitor は exit 0（門番にしない）＝docs/agent.md と一致。
- **verify 全体緑**（`成功（すべて通過）`・unit 508／integration 164／e2e 11・ruff・mypy strict・pm 検査）。指摘は
  上記 1 件（履歴引き継ぎの回帰テスト欠落）のみで、実装フェーズ内に修正済み。
