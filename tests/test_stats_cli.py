"""stats CLI（カタログ）の検査（T-0218）。

各カタログコマンドが登録済みの kind を一覧に出すことを確かめる（config に書ける語彙を人が確かめられる入口）。
カタログは軽い（numpy＋registry だけ）が、numpy を要するので stats/ds のどちらかの extra が要る＝importorskip。
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from typer.testing import CliRunner  # noqa: E402

from harness.stats.cli import stats_app  # noqa: E402

pytestmark = pytest.mark.integration

_runner = CliRunner()


def test_models_catalog_lists_residents() -> None:
    result = _runner.invoke(stats_app, ["models"])
    assert result.exit_code == 0
    assert "normal_mean" in result.stdout and "linear" in result.stdout


def test_samplers_catalog_lists_nutpie_and_pymc() -> None:
    result = _runner.invoke(stats_app, ["samplers"])
    assert result.exit_code == 0
    assert "nutpie" in result.stdout and "pymc" in result.stdout


def test_diagnostics_catalog_lists_kinds() -> None:
    result = _runner.invoke(stats_app, ["diagnostics"])
    assert result.exit_code == 0
    for kind in ("r_hat", "ess_bulk", "divergences"):
        assert kind in result.stdout


def test_ppc_catalog_lists_coverage() -> None:
    result = _runner.invoke(stats_app, ["ppc"])
    assert result.exit_code == 0
    assert "coverage_90" in result.stdout
