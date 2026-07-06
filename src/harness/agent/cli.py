"""agent プロファイルの CLI 入口（typer）。`uv run agent <サブコマンド>` で呼ぶ。

中核・ds・serve の CLI とはモジュールを分ける（プロファイル境界・DEC-0004）。重い依存
（実プロバイダの SDK 等）は各コマンドの中で遅延取り込みする（一覧系と --help を軽く保つ）。
`agent run --test` は合成 spec＋合成 cases のスモーク（無ネットワーク）＝「実験は --test 必須」の規律を
verify（tests/test_agent_e2e.py）に接続する。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from harness.registry import render_catalog

# Windows コンソール（cp932）でも日本語・記号を出せるよう UTF-8 に固定（ds/cli.py と同じ作法）。
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

agent_app = typer.Typer(help="LLM エージェント（AgentSpec）の開発・評価（agent プロファイル）", add_completion=False)


@agent_app.command("providers")
def _agent_providers() -> None:
    """プロバイダの一覧（PROVIDERS レジストリから生成）。AgentSpec の provider に書ける kind。"""
    from harness.agent.providers import PROVIDERS

    render_catalog(PROVIDERS)
    typer.echo("\nverify は dummy/cassette のみ（無ネットワーク・DEC-0015）。実プロバイダは `uv sync --extra agent`。")


@agent_app.command("metrics")
def _agent_metrics() -> None:
    """採点器の一覧（AGENT_METRICS レジストリから生成）。thresholds に書ける名前。"""
    from harness.agent.eval import AGENT_METRICS

    render_catalog(AGENT_METRICS, show_task=True)  # MetricEntry＝向き（大/小）の列が自動で付く
    typer.echo("\nthresholds に書くと passes が向き（大/小）を見て合否判定する（NaN は不合格＝fail closed）。")


@agent_app.command("run")
def _agent_run(
    spec: Annotated[Path | None, typer.Option("--spec", help="AgentSpec の宣言 YAML")] = None,
    input_text: Annotated[str | None, typer.Option("--input", help="ユーザ入力（1 発話）")] = None,
    test: Annotated[
        bool, typer.Option("--test", help="合成 spec＋合成 cases のスモーク（無ネットワーク・verify 用）")
    ] = False,
    seed: Annotated[int, typer.Option(help="乱数種（dummy の応答導出に混ぜる・明示必須の規約）")] = 0,
) -> None:
    """AgentSpec で 1 応答を出す。--test は --spec/--input を使わず組み込みスモークを回す。"""
    from harness.agent.providers import PROVIDERS, build_messages, reply_text

    if test:
        from harness.agent.experiment import run_agent_eval
        from harness.agent.spec import AgentSpec

        # 合成 spec＋3 件の合成 cases：replies で 2 件は一致・1 件はハッシュ応答＝不一致（2/3 は構成から導ける）。
        smoke_spec = AgentSpec(name="smoke", provider="dummy", model="dummy-model", system_prompt="そのまま返す")
        provider = PROVIDERS.resolve("dummy").factory(seed, replies={"ping": "pong", "挨拶": "こんにちは"})
        cases = [
            {"id": "s1", "input": "ping", "expected": "pong"},
            {"id": "s2", "input": "挨拶", "expected": "こんにちは"},
            {"id": "s3", "input": "miss", "expected": "（dummy はハッシュ文字列を返す＝不一致）"},
        ]
        result = run_agent_eval(
            smoke_spec, cases, provider=provider, metrics=("exact_match",), thresholds={"exact_match": 0.5}, seed=seed
        )
        typer.echo(f"exact_match={result.metrics['exact_match']:.3f}\tpassed={result.passed}\tn={result.n}")
        if not result.passed:
            raise typer.Exit(1)
        return

    if spec is None or input_text is None:
        typer.echo("--spec と --input が必要（または --test でスモーク）")
        raise typer.Exit(2)
    from harness.agent.spec import load_agent_spec

    agent_spec = load_agent_spec(spec)
    entry = PROVIDERS.resolve(agent_spec.provider)  # 未知 provider はここで候補一覧つき ValueError
    provider = entry.factory(seed)
    reply = provider.reply(messages=build_messages(input_text), tools=(), spec=agent_spec)
    typer.echo(reply_text(reply))


def agent_main() -> None:
    """`uv run agent` の入口。"""

    agent_app()
