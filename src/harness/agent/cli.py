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


@agent_app.command("tools")
def _agent_tools() -> None:
    """ツールの一覧（TOOLS レジストリから生成）。AgentSpec の tools に書ける kind。"""
    from harness.agent.tools import TOOLS

    render_catalog(TOOLS)
    typer.echo("\nツールは純関数（無ネットワーク・決定的）。宣言の tools[] は agent lint が実在を検査する。")


@agent_app.command("run")
def _agent_run(
    spec: Annotated[Path | None, typer.Option("--spec", help="AgentSpec の宣言 YAML")] = None,
    input_text: Annotated[str | None, typer.Option("--input", help="ユーザ入力（1 発話）")] = None,
    test: Annotated[
        bool, typer.Option("--test", help="合成 spec＋合成 cases のスモーク（無ネットワーク・verify 用）")
    ] = False,
    seed: Annotated[int, typer.Option(help="乱数種（dummy の応答導出に混ぜる・明示必須の規約）")] = 0,
) -> None:
    """AgentSpec で 1 実行（ツール往復ループ）。--test は --spec/--input を使わず組み込みスモークを回す。"""
    from harness.agent.providers import PROVIDERS
    from harness.agent.runtime import run_agent

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

        # ツール往復のスモーク：台本 dummy が calculator(add, 2, 3) を呼び、tool_result "5" を受けて答える
        # （2 ターン・期待は台本の構成から導ける。無ネットワークのまま往復ループを一巡する）。
        tool_spec = AgentSpec(
            name="smoke-tools",
            provider="dummy",
            model="dummy-model",
            system_prompt="計算はツールで行う",
            tools=("calculator",),
        )
        tool_provider = PROVIDERS.resolve("dummy").factory(
            seed,
            replies={
                "2と3を足して": {"tool_use": {"name": "calculator", "input": {"a": 2, "b": 3, "op": "add"}}},
                "tool_result:5": "答えは 5",  # 2+3=5 の結果を受けた続きの台本
            },
        )
        run = run_agent(tool_spec, "2と3を足して", provider=tool_provider, seed=seed)
        typer.echo(f"tool_loop: turns={run.turns}\ttools_used={','.join(run.tools_used)}\toutput={run.output}")
        if run.stop_reason != "end_turn" or run.tools_used != ("calculator",):
            raise typer.Exit(1)
        return

    if spec is None or input_text is None:
        typer.echo("--spec と --input が必要（または --test でスモーク）")
        raise typer.Exit(2)
    from harness.agent.spec import load_agent_spec

    agent_spec = load_agent_spec(spec)
    entry = PROVIDERS.resolve(agent_spec.provider)  # 未知 provider はここで候補一覧つき ValueError
    provider = entry.factory(seed)
    run = run_agent(agent_spec, input_text, provider=provider, seed=seed)
    typer.echo(run.output)
    # 実行の来歴は stderr（stdout は応答テキストだけ＝パイプで使える）。
    typer.echo(f"stop_reason={run.stop_reason}\tturns={run.turns}\ttools_used={','.join(run.tools_used)}", err=True)


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


@agent_app.command("monitor")
def _agent_monitor(
    log: Annotated[
        str, typer.Option("--log", help="エージェント実行ログの glob（root 相対）")
    ] = "artifacts/agent/runs/**/*.jsonl",
    since: Annotated[
        str | None, typer.Option("--since", help="この日付（YYYY-MM-DD・境界日を含む）以降の行だけ")
    ] = None,
    file_issue: Annotated[
        bool, typer.Option("--file-issue", help="non_end_turn_rate の帯が要注意以上なら課題を冪等起票")
    ] = False,
) -> None:
    """エージェント実行ログ（AGENT_LOG_FIELDS）の監視表を YAML で出す（拒否/打ち切り率・コスト分位・ツール頻度）。

    門番にしない（率は exit code に載せず band で人が読む・**常に exit 0**）。壊れ行は警告して読み飛ばす
    （n_skipped に出る）。--file-issue は帯が要注意/大変化のとき課題を 1 件だけ起票する（決定的タイトル
    `[agent-monitor] non_end_turn_rate <帯>` の open が既に在れば再起票しない＝冪等）。
    """
    from datetime import date

    import yaml

    from harness.agent import monitor as monitor_mod

    since_date: date | None = None
    if since is not None:
        try:
            since_date = date.fromisoformat(since)
        except ValueError as exc:
            raise typer.BadParameter(f"--since は YYYY-MM-DD 形式（受領: {since!r}）") from exc

    root = _root()
    files = sorted(root.glob(log))
    logs = monitor_mod.read_agent_logs(files, since=since_date)
    report = monitor_mod.monitor(logs)
    out: dict[str, object] = {"log": log, **report.to_dict()}
    typer.echo(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))

    if not file_issue:
        return
    band = monitor_mod.rate_band(report.non_end_turn_rate)
    if band == "安定":
        return
    from harness import issues

    # 冪等起票：決定的タイトルの open 課題が既に在れば作らない（二度叩いても 1 件・item.md の受け入れ基準）。
    title = f"[agent-monitor] non_end_turn_rate {band}"
    existing = [
        li for li in issues.load_issues(root) if li.issue.state is issues.IssueState.open and li.issue.title == title
    ]
    if existing:
        typer.echo(f"既存の open 課題あり: {existing[0].issue.id}（再起票しない）")
        return
    directory = issues.local_dir(root)
    if directory is None:  # github: backend＝起票は GitHub 側（issue new と同じ案内。監視は exit 0 のまま）
        typer.echo("github: backend では起票は GitHub 側で行う")
        return
    directory.mkdir(parents=True, exist_ok=True)
    iid = issues.next_id(root)
    # issue new（harness/cli.py）と同じファイル作法。title は '[' 始まりなので YAML として引用符で守る。
    body = (
        f"# {iid} {title}\n\n## 事象\n\n"
        f"non_end_turn_rate={report.non_end_turn_rate:.4f}（帯: {band}）・n_rows={report.n_rows}。\n\n"
        f"## 根拠・影響\n\n`uv run agent monitor` の集計（stop_reason 分布はログ参照）。"
        f"失敗/打ち切りの増加は品質かコストの異常の代理＝原因（プロンプト変更・ツール障害・上限設定）を確認する。\n"
    )
    path = directory / f"{iid}.md"
    meta = f'id: {iid}\nkind: risk\nstate: open\ncreated: {date.today().isoformat()}\ntitle: "{title}"'
    path.write_text(f"---\n{meta}\n---\n{body}", encoding="utf-8")
    typer.echo(f"起票: {path}")


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
