---
id: T-0091
kind: task
status: todo
title: ツール往復ループ（TOOLS＋runtime.step/run_agent＋AGENT_LOG_FIELDS・input_fingerprint を core へ）
created: 2026-07-06
depends_on: [T-0089]
verified_by: [tests/test_agent_runtime.py::test_run_agent_tool_loop_no_network]
---
# T-0091 ツール往復ループ（agent/runtime.py＝step/run_agent）

## 狙い（骨組みの「1 応答」を「ツールを使う複数ターン」に差し替える・verify 緑を保つ）
T-0089 は provider が 1 応答を返すだけ（tools は素通し）。実運用の LLM エージェントは
**ツールを呼ぶ→結果を渡す→また考える** を stop_reason に従って繰り返す。この一巡（純関数の往復ループ）と、
1 実行を JSONL に残す**ログ契約**（監視 T-0093 の入力）をここで作る。**核の制約は変わらず無ネットワーク**：
dummy provider がツール呼び出しを決定的に台本化できるようにして往復をテストする（実プロバイダは T-0092）。

## 受け入れ基準（`harness/fingerprint.py` 新規・`agent/{tools,runtime}.py` 新規・軽 import 規約＝DEC-0013）
- **`harness/fingerprint.py`（core へ引き上げ・DEC-0009 の二重管理排除）**：`input_fingerprint(payload: Mapping[str,Any]) -> str`
  を `serve/runtime.py` から**移設**（正準 JSON＝キー昇順・区切り最小・非 ASCII 素通しの sha256）。stdlib（json/hashlib）のみ＝軽い。
  `serve/runtime.py` は `from harness.fingerprint import input_fingerprint` に**差し替え・振る舞い不変**（既存の予測ログ出力がバイト同一であることをテストで固定）。agent もこれを再利用（serve を import しない＝プロファイル境界）。
- **`agent/tools.py`**：`TOOLS: Registry[ToolEntry]("ツール", catalog="agent tools")`。1 ツール＝名前＋`input_schema`（JSON Schema）＋
  **純粋・決定的な** Python 関数（`fn(**args) -> str`）。description は factory docstring 1 行目（DEC-0009）。骨組みでは
  無ネットワークで決定的なツールを 1〜2 個登録（例：`calculator`＝式でなく `{"a":int,"b":int,"op":"add|mul"}` を受けて数値文字列を返す）。
  `to_provider_tools(names) -> list[dict]`（PROVIDERS へ渡す tool 宣言形＝`{"name","description","input_schema"}` の並び）と
  `run_tool(name, args) -> str`（未登録・スキーマ不一致は ValueError）を用意。ネットワーク・ファイル I/O は禁止（verify を無ネットワークに保つ）。
- **`agent/runtime.py`（純関数の往復ループ）**：
  - `AGENT_LOG_FIELDS: dict[str,str]`＝JSONL 1 行の契約（正本）。キー例：`time`・`request_id`・`agent`（name/provider/model/prompt_fingerprint）・
    `input_fingerprint`（`harness.fingerprint` で再計算可）・`input`・`output`（最終テキスト）・`stop_reason`・`turns`・`tools_used`（呼んだツール名の並び）・`usage`（input/output tokens 合算）。`serve.PREDICTION_LOG_FIELDS` と同型の「キー集合ドリフトを止める」規律。
  - `@dataclass(frozen=True) AgentRun`：`output:str`・`stop_reason:str`・`turns:int`・`tools_used:tuple[str,...]`・`usage:dict[str,int]`・`messages:tuple[Mapping,...]`（会話履歴＝配信 T-0094 が使う）。
  - `run_agent(spec, user_input, *, provider, tools=TOOLS, seed, max_turns=None) -> AgentRun`：`build_messages` で開始し、
    provider に `to_provider_tools(spec.tools)` を渡して往復する。`stop_reason=="tool_use"` の間は content の tool_use ブロックを
    `run_tool` で実行し `tool_result` を messages に積んで継続。`end_turn`（or spec.max_turns 到達）で停止。usage を合算。
    max_turns 到達での打ち切りは `stop_reason="max_turns"` にして**黙って無限ループしない**（上限は spec.max_turns、引数 max_turns は上書き口）。
  - `build_log_row(run, *, spec, request_id, time) -> dict`：`AGENT_LOG_FIELDS` の契約どおり（キー集合がずれたら ValueError）。`input_fingerprint` は `harness.fingerprint` を使う。
- **DummyProvider のツール台本化（決定性・無ネットワークを保つ）**：dummy が tool_use を決定的に返せるようにする。
  設計案（実装裁量）：`replies` の値が dict `{"tool_use": {"name","input"}}` なら tool_use ブロックを 1 つ返す。直近メッセージが
  tool_result なら台本の続き（text）を返す。text の値はこれまでどおり。**グローバル種は使わない**（seed は引数）。これで
  「1 回ツールを呼んで結果を受けて答える」2 ターンを構成から作れる。
- **lint.py の tools[] 検査を接続（T-0089 で保留した宿題）**：spec の `tools[]` が **TOOLS に実在**するか静的検査（未登録は error・deploy_lint 同型）。空 tools は従来どおり無指摘。
- **CLI 導線（DEC-0009）**：`agent tools`（`render_catalog(TOOLS)`）を追加。`agent run` を `run_agent`（複数ターン）に差し替え、
  `--test` スモークにツール往復を 1 本含める（AGENTS「実験は --test 必須」）。
- **導線更新**：`docs/agent.md` に「ツールと往復ループ／ログ契約（AGENT_LOG_FIELDS）」の節と CLI 例。`experiment`/関連スキルに 1 行（LLM エージェントのツール込み評価も同じ `uv run agent run --test`）。

## この骨組みでやらないこと（soon・理由つき）
- **実プロバイダのツール往復は T-0092**：ここは dummy の台本で往復の骨格を固める。実 SDK 応答形状の検証は cassette で（無ネットワーク）。
- **並列ツール実行・ツールのエラー再試行方針**は now では単純化（順に実行・ツールが投げたら run_agent が ValueError で止める）。方針を増やすのは監視 T-0093 で必要が見えてから（YAGNI）。
- **guards の Registry 化はしない**（2 実装目で昇格＝item.md の釘）。

## 触ってよいファイル
`src/harness/fingerprint.py`（新規）・`src/harness/serve/runtime.py`（input_fingerprint を import に差し替え・**振る舞い不変**）・
`src/harness/agent/{tools.py,runtime.py}`（新規）・`src/harness/agent/{providers.py,lint.py,cli.py}`（dummy 台本・tools 検査・CLI）・
`docs/agent.md`（追記）・`.claude/skills/**`（1 行）・`tests/test_agent_runtime.py`（新規）＋必要なら
`tests/{test_agent_lint.py,test_serve_runtime.py 相当}`（fingerprint 移設の不変性・tools 検査）。`ds/**` は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_agent_runtime.py::test_run_agent_tool_loop_no_network`（**e2e** or **integration**）：dummy を
  「入力 X→calculator(add,2,3) を呼ぶ／tool_result 後→'答えは 5' を返す」と台本化。`run_agent` が turns==2・
  `tools_used==("calculator",)`・output に 5・`stop_reason=="end_turn"`。**socket を塞いでネットワーク 0 を断つ**（T-0089 同型）。期待値は台本の構成から導く。
- `input_fingerprint` 移設の不変性（**unit**）：同じ payload で `harness.fingerprint.input_fingerprint` と旧来の期待（正準 JSON の sha256 を構成から計算）が一致。serve の予測ログ行がキー・値ともに従来と同一（既存 serve テストが緑のまま）。
- `TOOLS`・（必要なら）新カタログの全項目に description（**unit**・DEC-0009）。`run_tool` 未登録名・スキーマ不一致は ValueError（**unit**）。
- `max_turns` 到達で `stop_reason=="max_turns"`・無限ループしない（**unit**・dummy が常に tool_use を返す台本）。
- `build_log_row` が `AGENT_LOG_FIELDS` の契約どおり・キー集合がずれたら ValueError（**unit**）。
- lint：spec が未登録 tool を指すと error・実在 tool（or 空）なら無指摘（**unit**・一時プロジェクト）。
- `import harness.agent` の軽さ（anthropic/fastapi/uvicorn/polars/sklearn 未ロード）を維持（**integration**・subprocess）。
- 期待値は台本・payload の構成から導く（金メッキ禁止）。`uv run verify` 全体緑。`verified_by` の名がテストに実在。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：往復ループが max_turns で確実に止まる＝変異で無限ループ/打ち切り漏れを検出・
input_fingerprint 移設で serve 出力がバイト不変・tools のスキーマ検証が実際に効く・run_agent がネットワークを一切触らない・
AGENT_LOG_FIELDS のキー集合ドリフトを build_log_row が止める・profile 軽 import 維持）
