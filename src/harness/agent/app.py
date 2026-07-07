"""champion（昇格済み AgentSpec）を配信する FastAPI アプリ（agent プロファイル）。

fastapi はこのモジュールの top で import する（profile.py/__init__.py からは辿られない＝
`import harness.agent` の軽 import を壊さない・subprocess テストで固定）。champion は起動時
（create_app）に読み込み、無ければ明示エラーで落とす（リクエスト時に初めて壊れる・黙って空で
立つ、をしない＝serve/app.py と同じ規律。`harness.serve` は import しない＝プロファイル境界）。

serve の `/predict`（予測 1 発）と違い、agent は **会話×ツール往復**＝`POST /invoke`（1 発話 →
run_agent の往復ループ → 最終応答）。1 実行ごとに AGENT_LOG_FIELDS の JSONL 行を
`artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl` へ追記する＝`agent monitor` がそのまま読める
（配信が監視の入力を生む＝宣言→評価→昇格→配信→監視のライフサイクルが閉じる）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from harness.agent import store
from harness.agent.providers import PROVIDERS
from harness.agent.runtime import agent_log_path, append_run_log, build_log_row, run_agent
from harness.agent.spec import spec_from_mapping


class InvokeRequest(BaseModel):
    """POST /invoke の本文。input＝ユーザ発話（1 発話。会話の永続・複数ターン履歴は later＝item.md）。"""

    input: str


def create_app(
    root: Path, *, work: str, name: str, version: str | None = None, seed: int = 0, log_dir: Path | None = None
) -> FastAPI:
    """champion（version 指定時はその版）を載せた FastAPI アプリを作る。

    - GET /health … 生存確認（載っているエージェントの name/work/version つき）。
    - GET /metadata … AgentRecord の来歴（spec・metrics・prompt_fingerprint・created）。path は出さない。
    - POST /invoke … `{"input": "<発話>"}` を run_agent（ツール往復ループ）に通す。空 input は 422
      （黙って 200 にしない）。成功時は 1 実行ごとに AGENT_LOG_FIELDS の JSONL
      （既定 artifacts/agent/runs/<name>/<YYYYMMDD>.jsonl）へ 1 行追記する。

    provider は**宣言（spec.provider）に従う**＝override 口は作らない（champion の宣言が正本。
    verify は provider=dummy の champion で無ネットワークのまま回る）。
    """
    if version is not None:
        record = store.load_agent(root, work=work, name=name, version=version)
    else:
        maybe = store.champion(root, work=work, name=name)
        if maybe is None:  # 起動時に明示エラー（黙って空で立たない＝serve.load_champion と同じ）
            raise ValueError(f"{work}/{name}: champion が無い（先に `uv run agent promote` で昇格する）")
        record = maybe
    # 保存済み宣言（dict）から検証つきで AgentSpec を復元する（temperature 拒否・未知キー・effort・
    # tools→tuple を load_agent_spec と共用＝検証を二重管理しない）。
    spec = spec_from_mapping(record.spec, source=f"{work}/{name}/{record.version}")
    provider = PROVIDERS.resolve(spec.provider).factory(seed)  # 未知 provider は起動時に候補つき ValueError

    app = FastAPI(title=f"harness agent {record.work}/{record.name}")
    # テスト・運用ツールが起動済みアプリから来歴を確認できるよう state にも持つ（handler は closure で参照）。
    app.state.record = record
    app.state.spec = spec

    @app.get("/health")
    def health() -> dict[str, Any]:
        """生存確認。何が載っているか（エージェントの版）まで返す＝取り違えの早期発見。"""
        return {
            "status": "ok",
            "agent": {"name": record.name, "work": record.work, "version": record.version},
        }

    @app.get("/metadata")
    def metadata() -> dict[str, Any]:
        """載っているエージェントの来歴（manifest の内容）。path はローカル事情なので出さない。"""
        return {
            "name": record.name,
            "work": record.work,
            "version": record.version,
            "spec": dict(record.spec),
            "metrics": dict(record.metrics),
            "prompt_fingerprint": record.prompt_fingerprint,
            "created": record.created,
        }

    @app.post("/invoke")
    def invoke(request: InvokeRequest) -> dict[str, Any]:
        """1 発話を会話×ツール往復（run_agent）に通し、最終応答＋実行来歴を返す（1 行ログを残す）。"""
        if not request.input.strip():
            raise HTTPException(status_code=422, detail="input が空（発話テキストを入れること）")
        run = run_agent(spec, request.input, provider=provider, seed=seed)
        request_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        row = build_log_row(run, spec=spec, request_id=request_id, time=now.isoformat())
        append_run_log(agent_log_path(root, name=record.name, log_dir=log_dir, when=now), row)
        return {
            "output": run.output,
            "stop_reason": run.stop_reason,
            "turns": run.turns,
            "tools_used": list(run.tools_used),
            "usage": dict(run.usage),
            "request_id": request_id,
            "agent": {"name": record.name, "work": record.work, "version": record.version},
        }

    return app
