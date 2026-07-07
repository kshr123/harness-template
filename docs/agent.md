# agent — LLM エージェント（AgentSpec）の開発・評価の契約と CLI 導線

LLMOps/AgentOps プロファイル（EP-22・DEC-0015）。中核アーティファクトは **1 エージェント＝1 宣言
（AgentSpec＝prompt＋model＋tools＋方針）**。ライフサイクルは ML と同型：宣言 → golden set → 採点 →
合否 → 保存 → 昇格 → 配信 → 監視。実装は `src/harness/agent/`（spec.py＝宣言・providers.py＝
プロバイダ抽象・tools.py＝ツール（TOOLS）・runtime.py＝往復ループとログ契約・eval.py＝採点器と合否・
goal.py＝goal-based 停止ゲート（`Goal`/`GoalGate`/`run_agent_to_goal`・EP-23）・
experiment.py＝評価の一巡・store.py＝保存と昇格・app.py＝配信・monitor.py＝監視・lint.py＝宣言の構造 lint・
cli.py＝入口）。

## 使い方

```
uv run agent providers                 # プロバイダ一覧（AgentSpec の provider に書ける kind）
uv run agent metrics                   # 採点器一覧（thresholds に書ける名前・向きつき）
uv run agent tools                     # ツール一覧（AgentSpec の tools に書ける kind）
uv run agent run --spec <yaml> --input "<発話>"   # 宣言で 1 実行（ツール往復ループ・骨組みは dummy のみ）
uv run agent run --spec <yaml> --input "<発話>" --goal-expected "<正解>"  # goal-based ループ（下の節）
uv run agent run --test                # 合成 spec のスモーク（評価＋ツール往復＋goal ループ・無ネットワーク・verify 用）
```

実プロバイダ（`provider: anthropic`）は `uv sync --extra agent` で SDK を入れて使う（下の節）。

## loops（trigger×stop×policy・DEC-0017）

Anthropic「Getting started with loops」の分類（**loop＝停止条件が満たされるまで作業サイクルを繰り返す
エージェント**。trigger（起動）×stop-condition（停止）×policy（方針）で 4 類型）を運用モデルの語彙として
正本化したもの（正本 DEC は `docs/decisions/DEC-0017-loops-operating-model.md`）。語彙（`Trigger`・
`StopDecision`・`StopCondition`）は core `src/harness/loops.py`（stdlib のみ・DEC-0013）。

| 類型 | trigger | stop | 対応する実装 |
| --- | --- | --- | --- |
| turn-based | 発話・`agent run` | provider の `end_turn`＋`max_turns` backstop | `runtime.run_agent`（既存の再解釈のみ） |
| goal-based | 呼び出し時に Goal を宣言 | 評価器ゲート（`AGENT_METRICS`＋`eval.passes`）合格 or `max_cycles` backstop | `agent/goal.py`（`Goal`/`GoalGate`/`run_agent_to_goal`＝**唯一の新規部品**・T-0095） |
| time-based | 時間間隔（cron/CI schedule・Claude 側 /loop・/schedule スキル） | cancel・無効化 | 雛形のみ（実行基盤は利用者環境。T-0097・outline） |
| proactive | event/schedule＋goal の合成 | タスク＝goal 達成で退場・routine＝無効化まで | `agent monitor --file-issue`（前半円のみ実装済み。T-0098・outline） |

**goal-based の停止は評価器ゲート**：モデルの `end_turn`（「完了した気になった」）を、宣言済みの評価器
（`AGENT_METRICS`＋`eval.passes`・fail closed）が検査し、未達なら続行を注入する（AGENTS 第一原則の
エージェント実行版）。`run_agent` を丸ごと再利用し、続行は `run_agent` の続行口 `prior_messages`
（会話履歴を保ったまま「続けろ」を注入する keyword-only 引数・省略時は従来どおり）で行う。

```python
from harness.agent.goal import Goal, GoalGate, run_agent_to_goal

goal = Goal(expected="正解", thresholds={"exact_match": 1.0})
run = run_agent_to_goal(spec, "問い", provider=provider, gate=GoalGate(goal=goal), seed=0, max_cycles=4)
run.cycles, run.stop_reason, run.gate_reasons  # 各サイクルの判定＝来歴
```

CLI からは `agent run` の拡張だけで届く（新しいコマンドは足さない・DEC-0016）：

```
uv run agent run --spec <yaml> --input "<発話>" --goal-expected "<正解>" \
    --goal-threshold exact_match=1.0 --max-cycles 4
```

stdout は最終応答のみ・来歴（`cycles`/`stop_reason`/`gate_reasons`）は stderr（既存 `agent run` と同じ
分離）。**goal 未達（`max_cycles` 打ち切り）は exit 1**（評価器が合格と言うまで完了にしない、を exit code
に写す＝`agent monitor` の「門番にしない」＝常に exit 0 とは役割が違う）。
**verify 経路は extra 無し・ネットワーク 0 で全機能が検証できる**（dummy/cassette のみ＝DEC-0015）。

## 実プロバイダ（anthropic）と記録再生（cassette）

どちらも `providers.py` の**共有 adapter** `_reply_from_anthropic`（Anthropic Messages API 応答 dict →
`ProviderReply` の純変換・欠損や未知 block は明示 ValueError）を通る＝変換の 1 か所をテストすれば
実呼び出しと再生の両方が守られる。

- **`anthropic`（実 Anthropic 呼び出し・verify 経路外）**：SDK は `reply()` 内で遅延 import＝
  `import harness.agent` は extra 無しでも軽いまま（DEC-0013・subprocess テストで固定）。API キーは環境変数
  から SDK が読む（コードでは読まない）。**temperature は送らない**（現行モデルはパラメータごと廃止＝
  送ると 400・DEC-0015）。決定性は `output_config={"effort": spec.effort}`＝宣言に固定した effort で作る。
- **`cassette`（記録再生・replay 専用・テスト/CI 用・`agent/cassette.py`）**：cassette＝JSON ファイル
  `{キー: 応答 dict（model_dump 相当）}`。キー＝`(model, system_prompt, messages, tools)` の正準 JSON の
  sha256（`cassette_key`＝`harness.fingerprint.input_fingerprint` を再利用）。記録が無いキーは ValueError
  （**fail closed**＝dummy へフォールバックしない）。record モードは無い（実記録はネットワーク＝verify 外。
  フィクスチャは API 契約から手で書く）＝実 SDK の応答形状が変わったら再記録で検知する形状ガード。
  path（記録 JSON）が必須のため `agent run` の宣言 provider には使えない（`factory(seed)` 規約＝
  path 省略は明示エラー）。テストからは `cassette(seed, path=…)` で作る。

## AgentSpec（宣言 YAML の契約）

正本は `src/harness/agent/spec.py`。キーはこれだけ（未知キーは読み込みで失敗＝extra forbid）：

| キー | 型 | 意味 |
| --- | --- | --- |
| `name` | str | エージェント名 |
| `provider` | str | PROVIDERS の kind（一覧は `uv run agent providers`） |
| `model` | str | モデル名（既定方針：`claude-opus-4-8`・高頻度は `claude-sonnet-5`＝DEC-0015） |
| `system_prompt` | str | システムプロンプト |
| `tools` | list[str]（省略可・既定 []） | TOOLS の kind（一覧は `uv run agent tools`・lint が実在を検査） |
| `effort` | low/medium/high/xhigh/max（既定 medium） | 推論の深さ。**宣言に固定**＝再現性の軸 |
| `max_turns` | int（既定 8） | ツール往復の上限（到達で `stop_reason="max_turns"` に打ち切り） |
| `output_schema` | mapping（省略可） | 構造化出力の JSON Schema（検証は `agent/guardrails.py` の `validate_output_schema`） |

**`temperature` は書けない**（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。書くと専用の
エラーで effort＋cassette への移行を案内する。

## ツールと往復ループ（TOOLS → run_agent・`agent/{tools,runtime}.py`）

1 ツール＝名前＋`input_schema`（JSON Schema）＋**純粋・決定的な** Python 関数（`fn(**args) -> str`）。
レジストリは `TOOLS`（骨組みは `calculator` のみ・一覧は `uv run agent tools`）。ネットワーク・ファイル
I/O をするツールは書かない（verify の無ネットワーク契約＝DEC-0015）。

- `to_provider_tools(names)`：provider へ渡す tool 宣言（`{"name","description","input_schema"}` の並び）。
- `run_tool(name, args)`：1 回実行して文字列を返す。未登録名・スキーマ不一致（required 欠け・未宣言キー）は
  ValueError（黙って捨てず実行前に止める）。
- `run_agent(spec, user_input, provider=, seed=, max_turns=None, prior_messages=()) -> AgentRun`：**ツールを
  呼ぶ→結果を渡す→また考える** を stop_reason に従って繰り返す純関数。`tool_use` の間は tool_result を
  messages に積んで継続、`end_turn` で停止。上限（`spec.max_turns`・引数は上書き口）到達は
  `stop_reason="max_turns"` で必ず打ち切る。結果は `AgentRun`（output・stop_reason・turns・tools_used・
  usage 合算・messages 全履歴）。`prior_messages`（keyword-only・既定 ()）は続行口：
  `[*prior_messages, *build_messages(user_input)]` で開始する＝会話の続きから始めたいとき（goal-based
  ループが「続けろ」を注入する。上の「loops」節）に渡す。省略時は従来どおり（後方互換）。
- dummy provider は replies の値に `{"tool_use": {"name","input"}}` を仕込むと tool_use を台本化できる
  （tool_result 後の続きは鍵 `"tool_result:<結果文字列>"`）＝往復ループを無ネットワークでテストできる。

## ログ契約（AGENT_LOG_FIELDS・1 実行＝JSONL 1 行）

正本は `agent/runtime.py` の `AGENT_LOG_FIELDS`（`serve.PREDICTION_LOG_FIELDS` と同型の「キー集合ドリフトを
止める」規律＝`build_log_row(run, spec=, request_id=, time=)` がキー集合の一致を検査する）。監視
（`agent monitor`・下の節）はこの契約だけに依存する。

| キー | 型・意味 |
| --- | --- |
| `time` | str（ISO 8601・UTC） |
| `request_id` | str（uuid4 hex） |
| `agent` | dict（name・provider・model・prompt_fingerprint＝system_prompt の sha256） |
| `input_fingerprint` | str（`{"input": 入力テキスト}` の正準 JSON の sha256。`harness.fingerprint.input_fingerprint` で再計算できる） |
| `input` | str（ユーザ入力＝messages 先頭の user テキストから復元） |
| `output` | str（最終応答テキスト） |
| `stop_reason` | str（end_turn ｜ max_turns＝上限打ち切り ｜ その他 provider の stop_reason） |
| `turns` | int（provider 呼び出し回数） |
| `tools_used` | list[str]（呼んだツール名・呼んだ順） |
| `usage` | dict（input_tokens・output_tokens＝全ターンの合算） |

`input_fingerprint` は中核 `harness/fingerprint.py`（serve の予測ログと同じ関数を共有＝T-0091 で
`serve/runtime.py` から移設・DEC-0009）。agent は serve を import しない（プロファイル境界）。

## 評価と合否（golden set → passes）

- `run_agent_eval(spec, cases, provider=, metrics=, thresholds=, seed=)`：cases（`[{id, input, expected}]`）を
  provider に通し、採点器（AGENT_METRICS・骨組みは `exact_match`）の**平均**を出して `passes` で合否
  （向きつき・NaN は不合格＝fail closed）。fold は無い（golden set 全体に 1 回）。
- 乱数は明示 `seed=` のみ（グローバル種禁止）。dummy provider は入力＋seed の正準 JSON ハッシュから
  決定的に応答する（ネットワーク・課金ゼロ）。

## 保存→昇格→champion→experiments（LLMOps のライフサイクル・`agent/store.py`）

ML の `ds/models.py` と同型だがプロファイル独立（`ds` を import しない・`harness.storage` のみ再利用）。
**非対称**：agent の実体は宣言そのもの＝バイナリが無いので保存形式（FORMATS）は無く、manifest 1 枚
（spec を config として畳み込み＋metrics＋`prompt_fingerprint`＝system_prompt の sha256＋git 来歴）が保存の全体。

- `save_agent(root, spec, work=, name=, metrics=)`：評価済み宣言を版（UTC タイムスタンプ・再利用しない）として
  `work/<work>/agents/<name>/<version>/manifest.yaml` に保存。保存は常に許す（負の結果も記録）。
- `promote_agent(root, work=, name=, version=, thresholds=, primary=)`：**絶対関門**（`agent.eval.passes`＝
  向きつき・NaN 不合格）かつ**相対関門**（現 champion に primary で勝つ・同点/負けは昇格しない）を満たす
  ときだけ `promotions/<decided>.yaml` を追記。primary の向きの正本は AGENT_METRICS（引数では受けない）。
- `champion(root, work=, name=)`：昇格記録の最新が指す版（無ければ None）。`load_agent`/`list_agents` も対で用意。

```
uv run agent promote --work E-0101 --name helper --version 20260706T090000000000Z \
    --primary exact_match --threshold exact_match=0.8      # 関門で落ちたら非ゼロ終了（メッセージに理由）
uv run agent champion --work E-0101 --name helper           # 現 champion（版＋metrics＋prompt_fingerprint）
uv run agent experiments --results work/…/results           # 変種比較（metrics_*.yaml の leaderboard）
```

`agent experiments` は `ds.experiment.leaderboard`（polars＋yaml の純関数）を CLI 内で遅延 import して
再利用する（結果記録の形式 `metrics_<variant>.yaml` は ML の実験と共通＝比較の作法を二重化しない）。

## 配信（`agent serve`・champion を FastAPI で出す・`agent/app.py`）

昇格済み champion を FastAPI で配信する（宣言→評価→昇格→**配信**→監視のライフサイクルが閉じる）。
serve プロファイルと同じ作法・別 app（`harness.serve` は import しない＝プロファイル境界・DEC-0004。
fastapi/uvicorn は extra `agent` に含む＝`uv sync --extra agent`）。予測 1 発の serve `/predict` と違い、
agent は**会話×ツール往復**＝`POST /invoke`（1 発話 → `run_agent` の往復ループ → 最終応答）。

- **起動時に champion を読み込む**（version 指定時はその版）。無い・宣言が壊れている・provider が未知なら
  起動時に明示エラー（黙って空で立たない）。保存済み宣言（dict）は `spec_from_mapping` で検証つきで
  AgentSpec に復元する（temperature 拒否・未知キー・effort の検証を YAML 読込と共用）。
- **provider は宣言（spec.provider）に従う**＝override 口は無い（champion の宣言が正本。verify は
  provider=dummy の champion で無ネットワークのまま回る・DEC-0015）。
- `POST /invoke`：本文 `{"input": "<発話>"}`。空 input は 422。返答は
  `{output, stop_reason, turns, tools_used, usage, request_id, agent:{name,work,version}}`。
- `GET /health`（生存＋載っている版）・`GET /metadata`（来歴＝spec・metrics・prompt_fingerprint・created）。
- **1 実行＝AGENT_LOG_FIELDS の JSONL 1 行**を既定 `artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl`
  （`--log-dir` で変更可）へ追記＝`agent monitor` の既定 glob がそのまま読む（配信が監視の入力を生む）。

```
uv run agent serve --work E-0101 --name helper              # champion を配信（無ければ起動時エラー）
uv run agent serve --work E-0101 --name helper --version 20260706T090000000000Z --port 8080
```

ストリーミング（SSE）・会話の永続・認証/レート制御は LLM ゲートウェイの関心＝この骨組みではやらない
（/invoke は 1 発話→1 応答。ツール往復は内部で回る）。

## 監視（`agent monitor`・門番にしない・`agent/monitor.py`）

実行ログ（上の AGENT_LOG_FIELDS の JSONL）だけを読み、**品質の代理（拒否/打ち切り率）・コスト
（トークン/ターンの分位）・ツール使用頻度**を YAML で出す。`ds/monitor`（`data monitor`）と同じ規律：
**門番にしない**（率は band＝安定/要注意/大変化（0.05/0.2 の目安）で人が読む・**常に exit 0**）・壊れ行や
契約違反行は警告して読み飛ばす（`n_skipped` に出る＝盲目になるより縮退）・消費するキー
（time/stop_reason/usage/turns/tools_used）だけ検証する。分位はニアレストランク法（補間しない）。
実装は stdlib のみ（numpy/polars/ds 非依存＝core の軽さと DEC-0004 の境界を保つ。基準分布との比較（psi）は
agent のログに基準特徴表が無いのでしない＝必要が 3 個目に見えたら DEC-0012 で core 昇格）。

```
uv run agent monitor                              # 既定 glob artifacts/agent/runs/**/*.jsonl
uv run agent monitor --since 2026-07-01           # 境界日を含む・YYYY-MM-DD
uv run agent monitor --file-issue                 # 帯が要注意以上なら課題を冪等起票
```

`--file-issue` は決定的タイトル `[agent-monitor] non_end_turn_rate <帯>` で起票し、同タイトルの open 課題が
既に在れば再起票しない（**冪等**＝二度叩いても 1 件。github: backend では起票せず案内だけ・exit 0 のまま）。

## ガードレール（`agent/guardrails.py`・入出力の入口だけ・委譲点を明示）

入出力を通す前に確かめる薄い層。共通の口は `Guard` Protocol（`check(text) -> GuardResult`＝ok・reason・
matches）。骨組みは 2 つだけ（Registry 化は 2 実装目で＝YAGNI）：

- `PiiRegexGuard`（入力ガードの**正規表現スタブ**）：email・電話番号を検出（見つかれば `ok=False`＋
  `matches`）。実際の PII 検出は検出モデルへ**委譲**（入口だけ作って委譲点を明示＝DEC-0009 の作法）。
- `validate_output_schema(output, schema)`（出力ガード）：出力を JSON として解釈し、JSON Schema の
  **最小部分集合**（トップレベル `type`・`required`・`properties` の型）だけ検証。`AgentSpec.output_schema`
  をそのまま渡せる。完全検証は jsonschema へ**委譲**（base 依存に無い＝必要になったら extra として足す）。

## 宣言の構造 lint（verify に接続）

`docs/agents/**/*.yaml` を yaml で読むだけ（実行しない）で、`provider` が PROVIDERS に・`tools[]` が
TOOLS に実在するかを検査する（`src/harness/agent/lint.py`・serve の deploy_lint と同型）。`docs/agents/`
が無いプロジェクトでは何も指摘しない（tools 無し・空も無指摘）。
