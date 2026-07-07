---
id: T-0094
kind: task
status: todo
created: 2026-07-07
depends_on: [T-0091, T-0093]
verified_by: [tests/test_agent_serve.py::test_invoke_runs_agent_and_appends_run_log]
---
# T-0094 配信（`agent serve`＝champion を FastAPI で出す・POST /invoke＝会話×ツール往復）

## 狙い（ライフサイクルの最後＝宣言→評価→昇格→**配信**→監視 を閉じる）
昇格済み champion（`store.champion`）を FastAPI で配信する。予測 1 発の serve `/predict` と違い、agent は
**会話×ツール往復**＝`POST /invoke`（1 発話→`run_agent` の往復ループ→最終応答）。配信は 1 実行ごとに
`AGENT_LOG_FIELDS` の JSONL を `artifacts/agent/runs/<name>/<日付>.jsonl` へ追記する＝T-0093 の `agent monitor`
がそのまま読める（配信が監視の入力を生む＝ライフサイクルが閉じる）。serve プロファイルと同じ作法・別 app・
プロファイル境界（DEC-0004＝`harness.serve` は import しない・依存だけ共有）・軽 import（DEC-0013）。

## 設計判断
- **配信 provider は宣言（spec.provider）に従う**（override を作らない）。champion の宣言が正本＝
  `PROVIDERS.resolve(spec.provider).factory(seed)` で組む。verify（無ネットワーク）は provider=dummy の
  champion で回す（応答は決定的ハッシュ＝serve が「起動時にモデルを載せる」のと同じ骨組み）。本番の
  champion は provider=anthropic を宣言する（実行時に実 SDK・遅延 import・verify 経路外＝T-0092）。
- **fastapi/uvicorn は `agent` extra に足す**（`serve` extra へ相乗りさせない）。理由：`agent serve` は agent
  プロファイルの一部で、agent を配信するのに ds/serve（モデル配信）extra を要求するのは驚き＝プロファイル
  独立（DEC-0004）に反する。fastapi/uvicorn は汎用の web 依存＝agent の正当な配信依存。版ピンの重複は
  extra ごとに依存を明示する既存作法の範囲。案内は `uv sync --extra agent`。
- **spec.py に `spec_from_mapping` を足す**（検証を 1 か所に）。`load_agent_spec(path)` は YAML を読んでこれに
  委譲。app は `AgentRecord.spec`（保存済み dict）から `spec_from_mapping` で AgentSpec を復元する
  （temperature 拒否・未知キー・effort・tools→tuple の検証を再利用＝二重管理しない・DEC-0009）。
- **ログの追記口は agent に持つ**（serve の append_jsonl を import しない＝境界）。`agent/runtime.py` に
  `agent_log_path`（`artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl`＝monitor 既定 glob と一致）と最小の
  JSONL 追記を足す（stdlib。serve の同名関数との小さな重複は境界維持の許容コスト＝git 来歴複製と同じ扱い。
  3 個目の消費が出たら core 昇格を DEC-0012 で判断）。

## 受け入れ基準
### `src/harness/agent/spec.py`（`spec_from_mapping` 追加・load_agent_spec を委譲に）
- `spec_from_mapping(raw: Mapping[str, Any], *, source: str = "<mapping>") -> AgentSpec`：現 `load_agent_spec` の
  検証本体（dict 判定・temperature 拒否・未知キー・effort 検査・tools→tuple）をここへ移す。エラー文言の
  ファイル名部分は `source` で差す。`load_agent_spec(path)` は `yaml.safe_load` して `spec_from_mapping(raw,
  source=str(path))` を返すだけにする（挙動不変＝既存テストが緑のまま）。

### `src/harness/agent/runtime.py`（配信のログ口・純関数・stdlib のみ）
- `agent_log_path(root, *, name: str, log_dir: Path | None = None, when: datetime | None = None) -> Path`：
  既定 `artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl`（UTC 日付で 1 ファイル。`agent monitor` の既定 glob
  `artifacts/agent/runs/**/*.jsonl` に一致）。log_dir を渡すと `<log_dir>/<YYYYMMDD>.jsonl`。
- `append_run_log(path: Path, row: Mapping[str, Any]) -> None`：JSONL に 1 行追記（親ディレクトリを作る・
  UTF-8・非 ASCII 素通し）。`build_log_row`（既存）の返り値をそのまま書ける。
- `AGENT_LOG_FIELDS` 契約・`build_log_row` は**変更しない**（追記口を足すだけ）。

### `src/harness/agent/app.py`（新規・fastapi は top import・profile/__init__ からは辿らせない）
- `create_app(root, *, work, name, version=None, seed=0, log_dir=None) -> FastAPI`：
  - champion（version 指定時はその版＝`load_agent`）を読む。無ければ**起動時に**明示エラー（黙って空で立てない
    ＝serve と同じ）。`AgentRecord.spec` から `spec_from_mapping` で AgentSpec 復元。
  - provider は宣言に従い `PROVIDERS.resolve(spec.provider).factory(seed)`。
  - `GET /health`：status＋載っている agent（name/work/version）。
  - `GET /metadata`：record の来歴（name/work/version/spec/metrics/prompt_fingerprint/created）。path は出さない。
  - `POST /invoke`：本文 `{"input": "<発話>"}`。空 input は 422（黙って 200 にしない）。`run_agent(spec, input,
    provider=provider, seed=seed)` を回し、`build_log_row` → `append_run_log(agent_log_path(...))` で 1 行残す。
    返す：`{output, stop_reason, turns, tools_used, usage, request_id, agent:{name,work,version}}`。
  - fastapi/pydantic/uuid/datetime を top import（`import harness.agent.app` が重いのは可＝profile 経路外）。
    `app.state` に record/spec を持たせて起動済みアプリから確認できるようにする（serve と同作法）。

### `src/harness/agent/cli.py`：`agent serve` コマンド（新規・uvicorn は遅延・extra 未導入を案内）
- 引数：--work・--name・--version・--host(127.0.0.1)・--port(8000)・--seed(0)・--log-dir・--root(".")。
- `import uvicorn` と `from harness.agent.app import create_app` は**コマンド内で遅延**。ImportError（extra 未導入）は
  `uv sync --extra agent` を案内して exit 1（生の栈を吐かない＝serve/cli と同作法）。`uvicorn.run(app, host, port)`。
- **導線必須**（coverage_lint が `agent serve` を強制）：docs/agent.md とスキルに使い方を書く（下記）。

### `pyproject.toml`：`agent` extra に fastapi/uvicorn を足す
- `agent = ["anthropic>=0.40", "fastapi>=0.139", "uvicorn>=0.50"]`（版は serve extra と同じピン）。コメントで
  「実プロバイダ（anthropic）＋配信（fastapi/uvicorn）。verify 経路は dummy/cassette で無ネットワーク」。

### 導線・ドキュメント（coverage_lint＝DEC-0016）
- `docs/agent.md`：配信の節（`agent serve`・POST /invoke（会話×ツール往復）・/health・/metadata・provider は宣言に
  従う・ログは `artifacts/agent/runs/**` へ＝`agent monitor` が読む＝ライフサイクルが閉じる）。
- `.claude/skills/agent/SKILL.md`：配信の 1〜2 行（`agent serve` の呼び方＋/invoke）。

## 触ってよいファイル
`src/harness/agent/{app.py（新規）,cli.py（serve 追加）,spec.py（spec_from_mapping）,runtime.py（ログ口 2 関数）}`・
`pyproject.toml`（agent extra）・`docs/agent.md`・`.claude/skills/agent/SKILL.md`・
`tests/test_agent_serve.py`（新規）。`serve/**`・`ds/**`・`AGENT_LOG_FIELDS`/`build_log_row` の契約は変更しない。
`agent/__init__.py`・`agent/profile.py` は**変更しない**（app を辿らせない＝軽 import を守る）。

## 検査（テスト先書き・構成から導く・マーカー必須・無ネットワーク）
- `test_agent_serve.py::test_invoke_runs_agent_and_appends_run_log`（**integration**・verified_by 正本）：一時
  プロジェクトに provider=dummy の champion を保存＋昇格（`store.save_agent`＋`promote_agent`＝既存 test の作法）。
  `create_app` を `fastapi.testclient.TestClient` で叩く：`POST /invoke {"input": "ping"}` が 200 で output/
  stop_reason/turns/usage/request_id を返す（dummy は決定的＝期待は構成から導ける）。さらに
  `artifacts/agent/runs/<name>/<日付>.jsonl` が 1 行できて、`monitor.read_agent_logs` で `n_rows==1`
  （配信→監視の結線＝ログが契約どおり）。
- `GET /health`・`GET /metadata` が版・来歴を返す（**integration**）。空 input は 422（**integration**）。
- champion 不在で `create_app` が起動時エラー（**integration**＝黙って空で立たない）。
- `spec_from_mapping`（**unit**）：`dataclasses.asdict(spec)` を往復して同じ AgentSpec になる・temperature/未知
  キー/不正 effort は ValueError（`load_agent_spec` の既存挙動が委譲後も不変）。
- 軽 import 維持（**integration**・既存 subprocess テスト）：`import harness.agent` で fastapi/uvicorn/anthropic 未ロード
  （app を __init__/profile から辿らせない）。※app を import する行はこのテストに足さない（足すと fastapi が載る）。
- coverage_lint 緑（`agent serve` の導線がスキル/docs に在る）。`uv run verify` 全体緑・`verified_by` 実在。

## この骨組みでやらないこと（later・理由つき）
- ストリーミング（SSE）・会話の永続（複数ターンの外部履歴）・認証/レート制御は LLM ゲートウェイの関心
  （item.md の later）。/invoke は 1 発話→1 応答（ツール往復は内部）にとどめる。
- 実 API 結合テストは verify に載せない（ネットワーク＝DEC-0015。実 provider の配信は本番・cassette で形を守る）。
- OpenTelemetry 実エクスポート・agent 版 Docker/K8s テンプレは配信が固まってから（item.md later）。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：champion 不在で起動時に落ちる・空 input が 422・/invoke がログを 1 行残し監視が
読める・spec_from_mapping が temperature/未知キーを弾く・provider は宣言に従う・`import harness.agent` が
fastapi/anthropic を載せない＝軽さと境界・ネットワーク 0）
