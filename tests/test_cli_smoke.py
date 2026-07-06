"""data CLI の CliRunner スモーク（typer の配線を end-to-end に叩く）。

test_catalog.py はコマンド関数を直接呼ぶだけで typer の配線（コマンド登録・引数解析・exit code）を
通らない。ここでは typer.testing.CliRunner で `data <サブコマンド>` を実際に解析させ、
未登録コマンドの取りこぼし・Option 解析の破れを止める。重い store 準備が要る predict の正常系は
test_cli_predict.py に任せ、ここは配線の smoke に絞る。

期待値はレジストリ登録から導く（代表項目＝各レジストリに実在する kind。金メッキ禁止）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from harness.ds.cli import data_app

pytestmark = pytest.mark.integration

runner = CliRunner()

# カタログ系コマンド → 代表項目（各レジストリに登録済みの kind。BLOCKS/ENCODERS/MODELS/METRICS/
# DATA_SOURCES/SELECTORS/TUNERS/DIMRED・CLUSTERERS・ANOMALY から選ぶ）。cwd 非依存（レジストリから生成）。
CATALOG_CASES = [
    ("blocks", "columns"),  # features.BLOCKS
    ("encoders", "onehot"),  # pipeline.ENCODERS
    ("models", "logreg"),  # pipeline.MODELS
    ("metrics", "roc_auc"),  # eval.METRICS
    ("sources", "synthetic"),  # data.DATA_SOURCES
    ("selectors", "selectkbest"),  # pipeline.SELECTORS
    ("tuners", "random"),  # tune.TUNERS
    ("unsupervised", "kmeans"),  # unsupervised.CLUSTERERS（dimred/cluster/anomaly の 3 レジストリを併記）
]


@pytest.mark.parametrize(("command", "expected"), CATALOG_CASES)
def test_catalog_commands_exit_zero_with_representative_item(command: str, expected: str) -> None:
    result = runner.invoke(data_app, [command])
    assert result.exit_code == 0, (
        f"data {command} が失敗: exit={result.exit_code} exc={result.exception!r} {result.output}"
    )
    assert expected in result.output, f"data {command} に代表項目 {expected} が載っていない"


def test_help_lists_all_subcommands() -> None:
    # --help に載る＝typer に登録されている（配線の証拠）。invoke で叩けない store 依存コマンド
    # （profile/compare/cluster/embed/anomaly/saved）は --help でしか登録漏れを検出できないので全部を対象にする。
    result = runner.invoke(data_app, ["--help"])
    assert result.exit_code == 0, f"data --help が失敗: {result.exception!r}"
    for command in (
        "lint",
        "list",
        "blocks",
        "encoders",
        "models",
        "sources",
        "profile",
        "compare",
        "unsupervised",
        "cluster",
        "embed",
        "anomaly",
        "metrics",
        "predict",
        "experiments",
        "selectors",
        "tuners",
        "saved",
    ):
        assert command in result.output, f"data --help に {command} が載っていない（コマンド未登録）"


def test_list_and_lint_run_in_project_root(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # list/lint は _root()=Path.cwd() を見るので cwd を一時プロジェクトの根へ移す。
    proj = make_project()
    proj.add_schema(
        {
            "id": "smoke_table",
            "description": "CliRunner スモーク用",
            "layer": "raw",
            "scope": "project",
            "primary_key": ["id"],
            "columns": [{"name": "id", "dtype": "Int64", "nullable": False, "unique": True}],
        }
    )
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, ["list"])
    assert result.exit_code == 0
    assert "smoke_table" in result.output  # add_schema で置いた定義が生成ビューに出る

    result = runner.invoke(data_app, ["lint"])
    assert result.exit_code == 0
    assert "問題なし" in result.output  # 正しい定義 1 つ＝エラー 0 件


def test_experiments_with_empty_results_dir_exits_zero(tmp_path: Path) -> None:
    # --results の Option 解析＋空ディレクトリの案内メッセージ（metrics_*.yaml が無い → exit 0）。
    empty = tmp_path / "results"
    empty.mkdir()
    result = runner.invoke(data_app, ["experiments", "--results", str(empty)])
    assert result.exit_code == 0
    assert "実験結果が無い" in result.output


def test_predict_without_required_options_fails() -> None:
    # 必須 Option（--work/--name/--table）欠落は typer（click）が usage error＝exit code 2 を返す。
    result = runner.invoke(data_app, ["predict"])
    assert result.exit_code == 2
