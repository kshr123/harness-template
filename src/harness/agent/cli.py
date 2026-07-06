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


def _root() -> Path:
    return Path.cwd()


def _parse_thresholds(pairs: list[str]) -> dict[str, float]:
    """`--threshold 名=値` の繰り返しを dict にする。形式不正は候補つきで止める（黙って捨てない）。"""
    out: dict[str, float] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise typer.BadParameter(f"--threshold は 名=値 の形式（実際: {pair!r}。例: exact_match=0.8）")
        try:
            out[name] = float(value)
        except ValueError as exc:
            raise typer.BadParameter(f"--threshold {name} の値が数値でない（実際: {value!r}）") from exc
    return out


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


@agent_app.command("promote")
def _agent_promote(
    work: Annotated[str, typer.Option(help="作業単位ID（保存先 work/<work>/agents/…）")],
    name: Annotated[str, typer.Option(help="エージェント名")],
    version: Annotated[str, typer.Option(help="昇格候補の版（UTC タイムスタンプ）")],
    primary: Annotated[str, typer.Option(help="相対関門の指標（AGENT_METRICS の kind・向きはレジストリが正本）")],
    threshold: Annotated[
        list[str], typer.Option("--threshold", help="絶対関門の閾値 名=値（繰り返し可。例: exact_match=0.8）")
    ],
) -> None:
    """評価済みの版を champion へ昇格する（絶対関門＝閾値・相対関門＝現 champion に primary で勝つ）。"""
    from harness.agent import store

    try:
        promo = store.promote_agent(
            _root(), work=work, name=name, version=version, thresholds=_parse_thresholds(threshold), primary=primary
        )
    except ValueError as exc:  # 関門で不合格（絶対/相対）・未登録 primary → 昇格しない＝非ゼロ終了
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    shown = "  ".join(f"{k}={v:.4f}" for k, v in sorted(promo.metrics.items()))
    typer.echo(f"昇格: {promo.work}/{promo.name}/{promo.version}（decided={promo.decided}）")
    typer.echo(f"primary={promo.primary}（higher_is_better={promo.higher_is_better}）  {shown}")
    typer.echo(f"前 champion: {promo.previous_version or 'なし（初回昇格）'}")


@agent_app.command("champion")
def _agent_champion(
    work: Annotated[str, typer.Option(help="作業単位ID")],
    name: Annotated[str, typer.Option(help="エージェント名")],
) -> None:
    """現 champion の版と metrics を表示する（昇格記録の最新が指す版・無ければ「champion なし」）。"""
    from harness.agent import store

    champ = store.champion(_root(), work=work, name=name)
    if champ is None:
        typer.echo(f"{work}/{name}: champion なし（まだ昇格していない）")
        return
    shown = "  ".join(f"{k}={v:.4f}" for k, v in sorted(champ.metrics.items()))
    typer.echo(f"★ {champ.work}\t{champ.name}\t{champ.version}\t{shown}")
    typer.echo(f"prompt_fingerprint={champ.prompt_fingerprint}")


@agent_app.command("experiments")
def _agent_experiments(
    results: Annotated[Path, typer.Option(help="実験の results ディレクトリ（metrics_*.yaml の置き場所）")],
    sort_by: Annotated[
        str | None, typer.Option(help="降順に並べる指標名（省略時は最初のファイルの最初の指標）")
    ] = None,
) -> None:
    """変種比較のリーダーボード（results/metrics_*.yaml を集約）。

    集約は `harness.ds.experiment.leaderboard` を遅延 import で再利用する（polars＋yaml の純関数で
    ds 特有型に非依存・CLI 経路なので重い import 可＝T-0090 の許容点。core への複製はしない）。
    """
    import polars as pl

    from harness.ds.experiment import leaderboard

    df = leaderboard(results, sort_by=sort_by)
    if df.height == 0:
        typer.echo(f"実験結果が無い（{results} に metrics_*.yaml が見つからない）")
        return
    with pl.Config(tbl_rows=-1):  # 全変種を出す（既定の 10 行省略だとリーダーボードの中位が「…」で消える）
        typer.echo(str(df))


def agent_main() -> None:
    """`uv run agent` の入口。"""

    agent_app()
