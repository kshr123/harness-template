"""stats プロファイルの CLI 入口（typer）。`uv run stats <サブコマンド>` で呼ぶ。

ベイズ統計モデリングのカタログ（レジストリの一覧＝config に書ける kind と意味）を出す。重い依存（pymc・
arviz）は各コマンドの中で遅延 import する（レジストリの定義自体は numpy＋registry だけ＝カタログは軽い）。
推論・診断・採用の使い方は docs/stats.md が正本。中核 CLI とはモジュールを分ける（プロファイル境界）。
"""

from __future__ import annotations

import typer

from harness.registry import render_catalog

stats_app = typer.Typer(help="ベイズ統計モデリング（stats プロファイル）のカタログ", add_completion=False)


@stats_app.command("models")
def _stats_models() -> None:
    """ベイズモデル（BAYES_MODELS）の一覧。config の model 節の kind に書ける名前と意味。"""
    from harness.stats.models import BAYES_MODELS

    render_catalog(BAYES_MODELS)
    typer.echo("\n推論は run_inference（既定 nutpie）・保存は netCDF・採用は LOO。診断は `uv run stats diagnostics`。")


@stats_app.command("samplers")
def _stats_samplers() -> None:
    """サンプラー（SAMPLERS）の一覧。既定は nutpie（離散潜在を含むモデルは pymc へ自動フォールバック）。"""
    from harness.stats.sampling import SAMPLERS

    render_catalog(SAMPLERS)
    typer.echo("\n既定は nutpie（PyMC 公式推奨）。決定性は seed。実体は `uv sync --extra stats`。")


@stats_app.command("diagnostics")
def _stats_diagnostics() -> None:
    """収束診断（BAYES_DIAGNOSTICS）の一覧。閾値は既存の value_threshold に書く（新 gate kind なし）。"""
    from harness.stats.diagnostics import BAYES_DIAGNOSTICS

    render_catalog(BAYES_DIAGNOSTICS)
    typer.echo("\nr_hat<=1.01・ess_bulk>=400・divergences<=0 の形で assess_convergence に渡す。")


@stats_app.command("ppc")
def _stats_ppc() -> None:
    """事後予測検査（PPC_CHECKS）の一覧。観測を事後予測がどれだけ覆うか（被覆率）で自信過剰を止める。"""
    from harness.stats.ppc import PPC_CHECKS

    render_catalog(PPC_CHECKS)
    typer.echo("\ncoverage_90 の下限（例 >=0.8）を assess_ppc に渡す（value_threshold・下限で判定）。")


def stats_main() -> None:
    """`uv run stats` の実体（typer アプリを起動する）。"""
    stats_app()
