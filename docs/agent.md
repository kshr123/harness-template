# agent — LLM エージェントの開発・評価・配信（契約と CLI）

LLM エージェントを、コードでなく **1 つの宣言**（AgentSpec＝プロンプト＋モデル＋
ツール＋方針の YAML）として作り、育て、配るためのプロファイル。宣言を
golden set（期待する出力つきの評価例集）で採点し、基準を満たした版だけを
champion（現在の採用版）に採用して配信・監視する。エージェントを作る・評価する・
運用する人が、手順と契約（宣言のキー・ログの行形式）を確かめるために読む Reference。

ライフサイクルは機械学習モデルと同型：**宣言 → golden set で採点 → 合否 → 保存 → 採用 → 配信 → 監視**。
検証（`uv run verify`）はネットワークを使わない：実 API の代わりに dummy（合成応答）と
cassette（実 API 応答を JSON に固定しておき、ネットワークなしで再生する記録再生の仕組み）だけで
全機能を確かめる。再現性の軸は effort（推論の深さの指定）を宣言に固定して作る
（現行モデルは temperature を受け付けないため。DEC-0015）。

実装は `src/harness/agent/`。役割ごとに 1 ファイル：

- `spec.py` … 宣言（AgentSpec）の型と読み込み
- `providers.py` … プロバイダ抽象（dummy・anthropic・cassette）
- `tools.py` … ツールのレジストリ（TOOLS）
- `runtime.py` … ツール往復ループ（run_agent）とログ契約（AGENT_LOG_FIELDS）
- `eval.py` … 採点器（AGENT_METRICS）と合否（passes）
- `judge.py` … LLM-judge（`RubricJudge`＝rubric 採点のテンプレとパース）
- `goal.py` … goal-based 停止ゲート（`Goal`/`GoalGate`/`run_agent_to_goal`。宣言の読み込みは
  `goal_from_mapping`/`load_goal`/`gate_from_goal`）
- `experiment.py` … 評価の一巡
- `store.py` … 保存と採用
- `app.py` … 配信（FastAPI）
- `monitor.py` … 監視
- `lint.py` … 宣言の構造 lint
- `cli.py` … CLI の窓口（コマンド）

## 使い方（How-to）

```
uv run agent providers                 # プロバイダ一覧（AgentSpec の provider に書ける kind）
uv run agent metrics                   # 採点器一覧（thresholds に書ける名前・向きつき）
uv run agent tools                     # ツール一覧（AgentSpec の tools に書ける kind）
uv run agent run --spec <yaml> --input "<発話>"   # 宣言で 1 実行（ツール往復ループ・骨組みは dummy のみ）
uv run agent run --spec <yaml> --input "<発話>" --goal-expected "<正解>"  # goal-based ループ（下の節）
uv run agent run --test                # 合成 spec のスモーク（評価＋ツール往復＋goal ループ・無ネットワーク・verify 用）
```

実プロバイダ（`provider: anthropic`）は `uv sync --extra agent` で SDK を入れて使う
（「実プロバイダと記録再生」の節）。作業手順の案内は `.claude/skills/agent/SKILL.md`。

## loops（trigger×stop×policy＝エージェント運用の語彙）

loops は「**停止条件が満たされるまで作業サイクルを繰り返す**」エージェント運用の語彙
（Anthropic「Getting started with loops」の分類）。trigger（何が起動するか）× stop（何が止めるか）×
policy（何を方針に動くか）の組で 4 類型に分ける。正本の決定は
`docs/decisions/DEC-0017-loops-operating-model.md`。語彙（`StopDecision`・`StopCondition`）は元は core の
`harness.loops` にあったが、実際に使うのが `agent/goal.py` の 1 か所だけだったため
`src/harness/agent/goal.py` へ畳み込んだ（DEC-0020。4 類型の分類自体はこの節と DEC-0017 が正本）。

| 類型 | trigger | stop | 対応する実装 |
| --- | --- | --- | --- |
| turn-based | 発話・`agent run` | provider の `end_turn`＋`max_turns` backstop | `runtime.run_agent`（既存の再解釈のみ） |
| goal-based | 呼び出し時に Goal を宣言 | 評価器ゲート（`AGENT_METRICS`＋`eval.passes`）合格 or `max_cycles` backstop | `agent/goal.py`（`Goal`/`GoalGate`/`run_agent_to_goal`＝**唯一の新規部品**） |
| time-based | 時間間隔（cron/CI schedule・Claude 側 /loop・/schedule スキル） | cancel・無効化 | `templates/schedule/`＋schedule_lint |
| proactive | event/schedule＋goal の合成 | タスク＝goal 達成で退場・routine＝無効化まで | `agent monitor --file-issue`（前半円のみ実装済み。T-0098・outline） |

**goal-based の停止は評価器ゲート（goal-based gate＝評価器が合格と言うまで続行させる停止判定）**：

- モデルの `end_turn`（モデル自身の「完了した」判断）をそのまま信用しない。
- 宣言済みの評価器（`AGENT_METRICS`＋`eval.passes`・
  fail-closed＝判定できないときは不合格に倒す）が出力を検査し、
  未達なら「続けろ」を注入して続行させる（「検証に合格して初めて完了」＝AGENTS 第一原則のエージェント実行版）。
- 実装は `run_agent` の丸ごと再利用。続行は keyword-only 引数 `prior_messages`（会話履歴を保ったまま
  続きから始める続行口。省略時は従来どおり）で行う。

```python
from harness.agent.goal import Goal, GoalGate, run_agent_to_goal

goal = Goal(expected="正解", thresholds={"exact_match": 1.0})
run = run_agent_to_goal(spec, "問い", provider=provider, gate=GoalGate(goal=goal), seed=0, max_cycles=4)
run.cycles, run.stop_reason, run.gate_reasons  # 各サイクルの判定＝由来
```

CLI からは `agent run` の拡張だけで届く（新しいコマンドは足さない・DEC-0016）：

```
uv run agent run --spec <yaml> --input "<発話>" --goal-expected "<正解>" \
    --goal-threshold exact_match=1.0 --max-cycles 4
```

- stdout は最終応答のみ。由来（`cycles`/`stop_reason`/`gate_reasons`）は stderr に出す
  （既存 `agent run` と同じ分離）。
- goal 未達のまま `max_cycles` に達したら **exit 1**。「評価器が合格と言うまで完了にしない」を exit code に
  写す（常に exit 0 の `agent monitor`＝処理を止めない、とは役割が違う）。
- verify 経路は extra 無し・ネットワーク 0 で全機能を検証できる（dummy/cassette のみ・DEC-0015）。

### llm_judge（自由文の成功基準をモデルに採点させる・goal の宣言化）

`exact_match` は答えが一意のときしか使えない。自由文の成功基準（「手順が 3 段で書かれている」等）は
**`llm_judge`**（`AGENT_METRICS` の 1 kind。実体は `agent/judge.py` の `RubricJudge`）で採点する。
`GoalGate` は metric 名でなく **entry の型**（`JudgeEntry` か否か）でだけ分岐する＝`exact_match` だけの
goal は無変更で動く。

goal は**宣言（YAML）が正本**（読み込みは `agent/goal.py` の `goal_from_mapping`/`load_goal`）。キーは
`expected`・`metrics`（既定 `["exact_match"]`）・`thresholds`・`judge`（judge 系 metric を使うときだけ）：

```yaml
expected: "手順が番号付きで3段になっていること"   # rubric（llm_judge の y_true 経路）
metrics: [llm_judge]
thresholds:
  llm_judge: 0.7
judge:
  provider: cassette        # dummy（テスト）｜ cassette（記録再生・要 path）｜ anthropic（実運用）
  model: claude-opus-4-8
  effort: medium             # 省略可（既定 medium）
  path: fixtures/judge.json  # provider: cassette のときだけ書ける
```

- **judge 系 metric（`llm_judge`）と `judge:` 節は必ず対**：片方だけは読み込みで ValueError。judge 系と
  `exact_match` 等の純関数系の併用も ValueError（`expected` の意味が二重になるため）。
- `parse_judge_score` は、judge の応答テキストが strip 後に裸の `0`〜`1`（小数可）の全文一致でなければ
  **NaN** を返す。散文からの数値抽出や範囲外の clamp はしない（応答ドリフトを隠さない）。NaN は
  `eval.passes` の既存規約でそのまま不合格（fail-closed・L-009）。
- cassette フィクスチャの鍵は `cassette_key(model=…, system_prompt=JUDGE_SYSTEM_PROMPT,
  messages=judge_messages(rubric, candidate), tools=[])`。`JUDGE_SYSTEM_PROMPT`/`judge_user_text` は
  コード固定＝宣言では変えられない（テンプレを変えると鍵がずれて fail-closed になる）。

```
uv run agent run --spec <yaml> --input "<発話>" --goal goal.yaml --max-cycles 4
```

**`--goal` と `--goal-expected` の併用は exit 2**（正本が二重になる二重管理を避ける）。それ以外の exit
規約（stdout=最終応答・stderr=由来・goal 未達は exit 1）は `--goal-expected` と同じ。

横展開（ds/serve/ops のどこに適用し・しないか）の正本は DEC-0018。

## 実プロバイダ（anthropic）と記録再生（cassette）

どちらも `providers.py` の**共有 adapter** `_reply_from_anthropic` を通る。これは Anthropic Messages API の
応答 dict を `ProviderReply` へ写す純変換（欠損や未知 block は明示 ValueError）で、変換の 1 か所を
テストすれば実呼び出しと再生の両方が守られる。

- **`anthropic`（実 Anthropic 呼び出し・verify 経路外）**：
  - SDK は `reply()` 内で遅延 import＝`import harness.agent` は extra 無しでも軽いまま
    （DEC-0013・subprocess テストで固定）。
  - API キーは環境変数から SDK が読む（コードでは読まない）。
  - **temperature は送らない**（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。決定性は
    `output_config={"effort": spec.effort}`＝宣言に固定した effort で作る。
- **`cassette`（記録再生・replay 専用・テスト/CI 用・`agent/cassette.py`）**：
  - cassette＝JSON ファイル `{キー: 応答 dict（model_dump 相当）}`。キーは
    `(model, system_prompt, messages, tools)` の正準 JSON（キー順・区切りを固定し、同じデータからは
    常に同じバイト列になる JSON）の sha256
    （`cassette_key`＝`harness.fingerprint.input_fingerprint` を再利用）。
  - 記録が無いキーは ValueError（**fail-closed**＝dummy へフォールバックしない）。
  - record モードは無い（実記録はネットワーク＝verify 外）。フィクスチャは API 契約から手で書く＝
    実 SDK の応答形状が変わったら再記録で検知する形状ガード。
  - path（記録 JSON）が必須のため `agent run` の宣言 provider には使えない（`factory(seed)` 規約＝
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
  messages に積んで継続し、`end_turn` で停止する。上限（`spec.max_turns`・引数は上書き口）到達は
  `stop_reason="max_turns"` で必ず打ち切る。結果は `AgentRun`（output・stop_reason・turns・tools_used・
  usage 合算・messages 全履歴）。`prior_messages`（keyword-only・既定 ()）は続行口：
  `[*prior_messages, *build_messages(user_input)]` で開始する＝会話の続きから始めたいとき（goal-based
  ループが「続けろ」を注入する。上の「loops」節）に渡す。省略時は従来どおり（後方互換）。
- dummy provider は replies の値に `{"tool_use": {"name","input"}}` を仕込むと tool_use を台本化できる
  （tool_result 後の続きは鍵 `"tool_result:<結果文字列>"`）＝往復ループを無ネットワークでテストできる。

## ログ契約（AGENT_LOG_FIELDS・1 実行＝JSONL 1 行）

正本は `agent/runtime.py` の `AGENT_LOG_FIELDS`。`serve.PREDICTION_LOG_FIELDS` と同型の「キー集合ドリフトを
止める」規律で、`build_log_row(run, spec=, request_id=, time=)` がキー集合の一致を検査する。監視
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

`input_fingerprint` は中核 `harness/fingerprint.py` の関数で計算する（serve の予測ログと同じ関数を共有＝
T-0091 で `serve/runtime.py` から移設・DEC-0009）。agent は serve を import しない（プロファイル境界）。

## 評価と合否（golden set → passes）

- `run_agent_eval(spec, cases, provider=, metrics=, thresholds=, seed=)`：cases（`[{id, input, expected}]`）を
  provider に通し、採点器（AGENT_METRICS・骨組みは `exact_match`）の**平均**を出して `passes` で合否を
  判定する（向きつき・NaN は不合格＝fail-closed）。fold は無い（golden set 全体に 1 回）。
- 乱数は明示 `seed=` のみ（グローバル種禁止）。dummy provider は入力＋seed の正準 JSON ハッシュから
  決定的に応答する（ネットワーク・課金ゼロ）。

## 保存→採用→champion→experiments（ライフサイクルの後半・`agent/store.py`）

評価済みの宣言は registry（保存済みの版の登録簿）に版として残し、
採用の合否判定（評価の合格基準）を通った版だけを champion にする。ML の
`ds/models.py` と同型だがプロファイル独立（`ds` を import しない・`harness.storage` のみ再利用）。
**非対称**が 1 つ：agent の実体は宣言そのもの＝バイナリが無いので保存形式（FORMATS）は無く、manifest 1 枚
（spec を config として畳み込み＋metrics＋`prompt_fingerprint`＝system_prompt の sha256＋git 由来）が
保存の全体。

- `save_agent(root, spec, work=, name=, metrics=)`：評価済み宣言を版（UTC タイムスタンプ・再利用しない）として
  `work/<work>/agents/<name>/<version>/manifest.yaml` に保存。保存は常に許す（負の結果も記録）。
- `promote_agent(root, work=, name=, version=, thresholds=, primary=)`：**絶対条件**（`agent.eval.passes`＝
  向きつき・NaN 不合格）かつ**相対条件**（現 champion に primary で勝つ・同点/負けは採用しない）を満たす
  ときだけ `promotions/<decided>.yaml` を追記。primary の向きの正本は AGENT_METRICS（引数では受けない）。
- `champion(root, work=, name=)`：採用記録の最新が指す版（無ければ None）。`load_agent`/`list_agents` も対で用意。

```
uv run agent promote --work E-0101 --name helper --version 20260706T090000000000Z \
    --primary exact_match --threshold exact_match=0.8      # 合否判定で落ちたら非ゼロ終了（メッセージに理由）
uv run agent champion --work E-0101 --name helper           # 現 champion（版＋metrics＋prompt_fingerprint）
uv run agent experiments --results work/…/results           # 変種比較（metrics_*.yaml の leaderboard）
```

`agent experiments` は `ds.experiment.leaderboard`（polars＋yaml の純関数）を CLI 内で遅延 import して
再利用する（結果記録の形式 `metrics_<variant>.yaml` は ML の実験と共通＝比較の作法を二重化しない）。

## 配信（`agent serve`・champion を FastAPI で出す・`agent/app.py`）

採用済み champion を FastAPI で配信する（宣言→評価→採用→**配信**→監視のライフサイクルが閉じる）。
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
- `GET /health`（生存＋載っている版）・`GET /metadata`（由来＝spec・metrics・prompt_fingerprint・created）。
- **1 実行＝AGENT_LOG_FIELDS の JSONL 1 行**を既定 `artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl`
  （`--log-dir` で変更可）へ追記＝`agent monitor` の既定 glob がそのまま読む（配信が監視の入力を生む）。

```
uv run agent serve --work E-0101 --name helper              # champion を配信（無ければ起動時エラー）
uv run agent serve --work E-0101 --name helper --version 20260706T090000000000Z --port 8080
```

ストリーミング（SSE）・会話の永続・認証/レート制御は LLM ゲートウェイの関心＝この骨組みではやらない
（/invoke は 1 発話→1 応答。ツール往復は内部で回る）。

## 監視（`agent monitor`・処理を止めない・`agent/monitor.py`）

実行ログ（上の AGENT_LOG_FIELDS の JSONL）だけを読み、**品質の代理（拒否/打ち切り率）・コスト
（トークン/ターンの分位）・ツール使用頻度**を YAML で出す。`ds/monitor`（`data monitor`）と同じ規律で作る：

- **処理を止めない**：率は band（安定/要注意/大変化の 3 段の重大度の帯。0.05/0.2 の目安）で
  人が読む。exit code は常に 0（自動停止しない）。
- **壊れ行・契約違反行は警告して読み飛ばす**（件数は `n_skipped` に出る）。全体が読めなくなるより縮退を選ぶ。
- **消費するキー（time/stop_reason/usage/turns/tools_used）だけ検証する**。
- 分位はニアレストランク法（補間しない）。実装は stdlib のみ（numpy/polars/ds 非依存＝core の軽さと
  DEC-0004 の境界を保つ）。
- 基準分布との比較（PSI＝Population Stability Index。分布のずれを測る監視指標）はしない：agent のログには基準特徴表が無い。必要が 3 個目に
  見えたら DEC-0012 の流れで core 採用を検討する。

```
uv run agent monitor                              # 既定 glob artifacts/agent/runs/**/*.jsonl
uv run agent monitor --since 2026-07-01           # 境界日を含む・YYYY-MM-DD
uv run agent monitor --file-issue                 # 帯が要注意以上なら課題を冪等起票
```

`--file-issue` は決定的タイトル `[agent-monitor] non_end_turn_rate <帯>` で起票し、同タイトルの open 課題が
既に在れば再起票しない（**冪等**＝二度叩いても 1 件。github: backend では起票せず
案内だけ・exit 0 のまま）。

## time-based routine（monitor の定期実行・templates/schedule/）

`agent monitor` を時間間隔で定期実行するための雛形が `templates/schedule/`（`monitor.yml`＋`README.md`）に
ある。**実行基盤（GitHub Actions・cron・Claude 側の `/loop`・`/schedule` スキル）は利用者環境が持つ**
（ハーネスは実行基盤を再発明しない＝DEC-0006/0008）。使い方：

1. `templates/schedule/monitor.yml` を案件リポジトリの `.github/workflows/` へコピーする
   （**このリポジトリ自身の `.github/workflows/` には置かない**＝verify は時間起動を含まない、実 schedule
   は動かさない）。
2. `on.schedule.cron` を運用に合わせて調整する（UTC・5 フィールド）。
3. push すると、次の cron 起動（または `workflow_dispatch` の手動実行）から `uv run agent monitor
   --file-issue` が定期的に走る。

Claude 側で回したいときは `/loop`（間隔指定の繰り返し）や `/schedule`（cron 起動の routine）スキルから
同じ雛形の運用思想（trigger×stop）に沿って組む（実行基盤としては別の経路・雛形自体は共通）。

### 停止（stop）

**「止め方の無い routine を作らない」**＝停止手順が無い定期実行は作らない、という規律。次のいずれかで
止める：

- GitHub の Actions 画面で workflow を **Disable workflow**、または `gh workflow disable` で無効化する。
- コピー先の `.github/workflows/monitor.yml` を削除する。
- Claude 側で組んだ場合はそのスキル/スケジュールを解除する。
- 補足：GitHub は 60 日間 push が無い scheduled workflow を自動的に無効化する。

この規律は `src/harness/agent/schedule_lint.py`（`uv run verify` で走る）が機械的に守る：雛形に
「停止」を含むコメント（README/docs 参照つき）と `README.md` の停止見出しが無ければ error になる
（停止宣言の欠落は verify で失敗＝レビューを待たずに検知する）。

## proactive 閉ループ（前半円＋後半円）

proactive（event/schedule＋goal の合成。写像表は `work/EP-23-loops/item.md`）は 2 つの半円からなる：
**前半円**（監視→冪等起票）は `agent monitor --file-issue` で実装済み。**後半円**（issue→修正→検証緑で
close）は新しいコード・新しい CLI を足さずに、既存の合否判定（`issues.run_checks` の不変条件＋monitor の
再起票）だけで閉じる。

### フロー（maker-checker＝作る側と確かめる側を分ける原則、の承認点つき）

1. **front**：`agent monitor --file-issue` が帯（`non_end_turn_rate`）が要注意以上のとき決定的タイトルで
   冪等に起票する（exit 0 のまま・処理を止めない）。
2. **[承認点 1] 人の triage**：`uv run issue list --open` で open 課題を拾い、対処するか
   （`promoted_to` にタスク ID を書いて in-progress にする）見送るか（`wontfix`＋「## 理由」）を人が決める。
3. **maker**：拾った課題を修正するタスクを実装する。
4. **checker**：review スキル（独立レビュー）＋`uv run verify` 緑。作った本人・同じ文脈のエージェントが
   自分で合否判定しない（AGENTS 第一原則）。
5. **[承認点 2] 人が退場を確定**：タスクの `status: done` と課題の `state: resolved` を同一コミットで
   確定する（`issues.run_checks` が resolved⟺promoted_to done を両向きで強制＝片方だけの更新は error）。

### 退場条件（goal）＝固定 2 条件

課題の起票 body に付く「## 退場条件（goal）」節（固定文・機械はこの節自体を読まない）が明記する条件は
常にこの 2 つ：

- (i) `promoted_to` タスクが **done**（`issues.run_checks` が resolved⟺done の不変条件を機械強制）。
- (ii) 次回の `agent monitor --file-issue` で帯が「安定」に戻り**再起票されない**。resolved 後も帯が悪ければ
  同じ決定的タイトルで新しい課題が立つ＝「再起票＝goal 未達の機械判定」（前半円が後半円の checker を兼ねる）。

停止（いつ routine 自体を止めるか）は上の「停止（stop）」節の規律にそのまま合流する（重複記述しない）。

### やらないこと

- **自律 auto-fix を作らない**：issue を機械が読んで修正を生成・適用・close する経路をハーネスに置かない。
- **承認無しの自動 merge を作らない**：承認点 1・2 は常に人。
- **`issue promote`/`issue close` の CLI を作らない**：状態遷移（`promoted_to`・`state`）は frontmatter の
  手編集＝人の行為が唯一の口。
- **monitor は exit 0 のまま**（処理を止めない＝起票は副作用という既存規律を壊さない）。

## ガードレール（`agent/guardrails.py`・入出力の受け口だけ・委譲点を明示）

入出力を通す前に確かめる薄い層。共通の口は `Guard` Protocol（`check(text) -> GuardResult`＝ok・reason・
matches）。骨組みは 2 つだけ（Registry 化は 2 実装目で＝YAGNI）：

- `PiiRegexGuard`（入力ガードの**正規表現スタブ**）：email・電話番号を検出（見つかれば `ok=False`＋
  `matches`）。実際の PII 検出は検出モデルへ**委譲**（受け口だけ作って委譲点を明示＝DEC-0009 の作法）。
- `validate_output_schema(output, schema)`（出力ガード）：出力を JSON として解釈し、JSON Schema の
  **最小部分集合**（トップレベル `type`・`required`・`properties` の型）だけ検証。`AgentSpec.output_schema`
  をそのまま渡せる。完全検証は jsonschema へ**委譲**（base 依存に無い＝必要になったら extra として足す）。

## 宣言の構造 lint（verify に接続）

`docs/agents/**/*.yaml` を yaml で読むだけ（実行しない）で、`provider` が PROVIDERS に・`tools[]` が
TOOLS に実在するかを検査する（`src/harness/agent/lint.py`・serve の deploy_lint と同型）。`docs/agents/`
が無いプロジェクトでは何も指摘しない（tools 無し・空も無指摘）。
