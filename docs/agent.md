# agent — LLM エージェント（AgentSpec）の開発・評価の契約と CLI 導線

LLMOps/AgentOps プロファイル（EP-22・DEC-0015）。中核アーティファクトは **1 エージェント＝1 宣言
（AgentSpec＝prompt＋model＋tools＋方針）**。ライフサイクルは ML と同型：宣言 → golden set → 採点 →
合否 → 保存 → 昇格（配信・監視は後続タスク）。実装は `src/harness/agent/`（spec.py＝宣言・providers.py＝
プロバイダ抽象・tools.py＝ツール（TOOLS）・runtime.py＝往復ループとログ契約・eval.py＝採点器と合否・
experiment.py＝評価の一巡・store.py＝保存と昇格・lint.py＝宣言の構造 lint・cli.py＝入口）。

## 使い方

```
uv run agent providers                 # プロバイダ一覧（AgentSpec の provider に書ける kind）
uv run agent metrics                   # 採点器一覧（thresholds に書ける名前・向きつき）
uv run agent tools                     # ツール一覧（AgentSpec の tools に書ける kind）
uv run agent run --spec <yaml> --input "<発話>"   # 宣言で 1 実行（ツール往復ループ・骨組みは dummy のみ）
uv run agent run --test                # 合成 spec のスモーク（評価＋ツール往復・無ネットワーク・verify 用）
```

実プロバイダ（`provider: anthropic`）は `uv sync --extra agent` で SDK を入れて使う（下の節）。
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
| `output_schema` | mapping（省略可） | 構造化出力の JSON Schema（検証は T-0093） |

**`temperature` は書けない**（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。書くと専用の
エラーで effort＋cassette への移行を案内する。

## ツールと往復ループ（TOOLS → run_agent・`agent/{tools,runtime}.py`）

1 ツール＝名前＋`input_schema`（JSON Schema）＋**純粋・決定的な** Python 関数（`fn(**args) -> str`）。
レジストリは `TOOLS`（骨組みは `calculator` のみ・一覧は `uv run agent tools`）。ネットワーク・ファイル
I/O をするツールは書かない（verify の無ネットワーク契約＝DEC-0015）。

- `to_provider_tools(names)`：provider へ渡す tool 宣言（`{"name","description","input_schema"}` の並び）。
- `run_tool(name, args)`：1 回実行して文字列を返す。未登録名・スキーマ不一致（required 欠け・未宣言キー）は
  ValueError（黙って捨てず実行前に止める）。
- `run_agent(spec, user_input, provider=, seed=, max_turns=None) -> AgentRun`：**ツールを呼ぶ→結果を渡す→
  また考える** を stop_reason に従って繰り返す純関数。`tool_use` の間は tool_result を messages に積んで継続、
  `end_turn` で停止。上限（`spec.max_turns`・引数は上書き口）到達は `stop_reason="max_turns"` で必ず打ち切る。
  結果は `AgentRun`（output・stop_reason・turns・tools_used・usage 合算・messages 全履歴）。
- dummy provider は replies の値に `{"tool_use": {"name","input"}}` を仕込むと tool_use を台本化できる
  （tool_result 後の続きは鍵 `"tool_result:<結果文字列>"`）＝往復ループを無ネットワークでテストできる。

## ログ契約（AGENT_LOG_FIELDS・1 実行＝JSONL 1 行）

正本は `agent/runtime.py` の `AGENT_LOG_FIELDS`（`serve.PREDICTION_LOG_FIELDS` と同型の「キー集合ドリフトを
止める」規律＝`build_log_row(run, spec=, request_id=, time=)` がキー集合の一致を検査する）。後続の監視
（T-0093）はこの契約だけに依存する。

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

## 宣言の構造 lint（verify に接続）

`docs/agents/**/*.yaml` を yaml で読むだけ（実行しない）で、`provider` が PROVIDERS に・`tools[]` が
TOOLS に実在するかを検査する（`src/harness/agent/lint.py`・serve の deploy_lint と同型）。`docs/agents/`
が無いプロジェクトでは何も指摘しない（tools 無し・空も無指摘）。
