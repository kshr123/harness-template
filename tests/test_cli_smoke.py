"""data CLI の CliRunner スモーク（typer の配線を end-to-end に叩く）。

test_catalog.py はコマンド関数を直接呼ぶだけで typer の配線（コマンド登録・引数解析・exit code）を
通らない。ここでは typer.testing.CliRunner で `data <サブコマンド>` を実際に解析させ、
未登録コマンドの取りこぼし・Option 解析の破れを止める。重い store 準備が要る predict の正常系は
test_cli_predict.py に任せ、ここは配線の smoke に絞る。

期待値はレジストリ登録から導く（代表項目＝各レジストリに実在する kind。ハードコード期待値禁止）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from harness.ds import store
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


def test_profile_with_target_adds_mutual_information_and_leakage(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 仕込みは構成から導く：leak は y と内容一致（Int64 のコピー）→ duplicate_of_target と |r|=1 の
    # high_correlation が確定。id は一意数=行数の整数 → id_like。x は独立な数値（挙がる理由が無い）。
    proj = make_project()
    proj.add_schema(
        {
            "id": "leaky_table",
            "description": "profile --target の MI/leakage スモーク用",
            "layer": "processed",
            "scope": "project",
            "primary_key": ["id"],
            "columns": [
                {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
                {"name": "x", "dtype": "Float64", "nullable": False},
                {"name": "leak", "dtype": "Int64", "nullable": False},
                {"name": "y", "dtype": "Int64", "nullable": False},
            ],
        }
    )
    rng = np.random.default_rng(0)
    y = np.array([0, 1] * 50, dtype=np.int64)
    df = pl.DataFrame({"id": np.arange(100), "x": rng.normal(size=100), "leak": y, "y": y})
    store.save(proj.root, df, "leaky_table")
    monkeypatch.chdir(proj.root)

    result = runner.invoke(data_app, ["profile", "leaky_table", "--target", "y", "--seed", "0"])
    assert result.exit_code == 0, f"data profile --target が失敗: exc={result.exception!r} {result.output}"
    out = dict(yaml.safe_load(result.output))
    assert "correlations" in out  # 既存の --target 出力は不変（追加のみ）

    # mutual_information：既定の対象＝数値列から target を除いた集合（関数の既定どおり）・列は feature/mi。
    mi_rows = out["mutual_information"]
    assert {r["feature"] for r in mi_rows} == {"id", "x", "leak"}
    assert all(set(r) == {"feature", "mi"} for r in mi_rows)

    # leakage：列 = column/reason/detail。仕込みどおりの (列, 理由) が挙がり、無害な x は挙がらない。
    leak_rows = out["leakage"]
    assert all(set(r) == {"column", "reason", "detail"} for r in leak_rows)
    reasons = {(r["column"], r["reason"]) for r in leak_rows}
    assert ("leak", "duplicate_of_target") in reasons
    assert ("leak", "high_correlation") in reasons  # y のコピー＝|r|=1.0（>= 既定 0.95）
    assert ("id", "id_like") in reasons
    assert "x" not in {c for c, _ in reasons}

    # --target なしの既存出力に新キーは足さない（既存コマンド・表示は不変）。
    result_plain = runner.invoke(data_app, ["profile", "leaky_table"])
    assert result_plain.exit_code == 0
    out_plain = dict(yaml.safe_load(result_plain.output))
    assert "mutual_information" not in out_plain
    assert "leakage" not in out_plain


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
