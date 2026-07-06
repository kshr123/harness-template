"""実験リーダーボード（experiment.leaderboard / data experiments）のテスト。

results/metrics_<variant>.yaml を手で構成し、集約表の行・列・並び（構成した値の大小から導く）を確かめる。
時刻・乱数は使わない（決定的）。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
import yaml

from harness.ds.experiment import leaderboard


def _write_metrics(
    results_dir: Path,
    variant: str,
    metrics: dict[str, float],
    *,
    passed: bool = True,
    version: str = "v1",
) -> None:
    """実験スクリプトが残す results/metrics_<variant>.yaml と同じ形を書く。"""
    payload = {
        "variant": variant,
        "metrics": metrics,
        "passed": passed,
        "model": {"name": variant, "version": version},
    }
    (results_dir / f"metrics_{variant}.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


@pytest.mark.unit
def test_leaderboard_aggregates_and_sorts_descending(tmp_path: Path) -> None:
    """3 変種の roc_auc を 0.90/0.95/0.85 で構成 → 降順は b(0.95), a(0.90), c(0.85)。"""
    _write_metrics(tmp_path, "a", {"roc_auc": 0.90}, passed=True, version="va")
    _write_metrics(tmp_path, "b", {"roc_auc": 0.95}, passed=True, version="vb")
    _write_metrics(tmp_path, "c", {"roc_auc": 0.85}, passed=False, version="vc")
    df = leaderboard(tmp_path)
    assert df.height == 3
    assert {"variant", "passed", "model_version", "roc_auc"} <= set(df.columns)
    # 未指定の既定＝最初のファイル（metrics_a.yaml）の最初の指標 roc_auc で降順
    assert df["variant"].to_list() == ["b", "a", "c"]
    assert df["roc_auc"].to_list() == [0.95, 0.90, 0.85]
    assert df["passed"].to_list() == [True, True, False]
    assert df["model_version"].to_list() == ["vb", "va", "vc"]
    # sort_by を明示しても同じ並び
    assert leaderboard(tmp_path, sort_by="roc_auc")["variant"].to_list() == ["b", "a", "c"]


@pytest.mark.unit
def test_leaderboard_union_columns_fills_null(tmp_path: Path) -> None:
    """一方は f1 のみ・他方は roc_auc のみ → 和集合の列になり、無い所は null。"""
    _write_metrics(tmp_path, "a", {"f1": 0.7})
    _write_metrics(tmp_path, "b", {"roc_auc": 0.9})
    df = leaderboard(tmp_path)
    assert {"f1", "roc_auc"} <= set(df.columns)
    # 既定ソート＝最初のファイル（metrics_a.yaml）の f1 で降順・null は末尾 → a, b
    assert df["variant"].to_list() == ["a", "b"]
    assert df.filter(pl.col("variant") == "a")["roc_auc"].to_list() == [None]
    assert df.filter(pl.col("variant") == "b")["f1"].to_list() == [None]


@pytest.mark.unit
def test_leaderboard_missing_fields_fall_back(tmp_path: Path) -> None:
    """variant・passed・model が無いファイル → variant はファイル名 stem から補完、他は null。"""
    (tmp_path / "metrics_x.yaml").write_text(yaml.safe_dump({"metrics": {}}), encoding="utf-8")
    df = leaderboard(tmp_path)
    assert df["variant"].to_list() == ["x"]
    assert df["passed"].to_list() == [None]
    assert df["model_version"].to_list() == [None]


@pytest.mark.unit
def test_leaderboard_no_metrics_sorts_by_variant(tmp_path: Path) -> None:
    """指標が 1 つも無い → variant 昇順（b, a の順で書いても a, b）。"""
    (tmp_path / "metrics_b.yaml").write_text(yaml.safe_dump({"variant": "b"}), encoding="utf-8")
    (tmp_path / "metrics_a.yaml").write_text(yaml.safe_dump({"variant": "a"}), encoding="utf-8")
    df = leaderboard(tmp_path)
    assert df["variant"].to_list() == ["a", "b"]


@pytest.mark.unit
def test_leaderboard_empty_dir_returns_empty_table(tmp_path: Path) -> None:
    """metrics_*.yaml が無い → 空表（固定 3 列・落ちない）。"""
    df = leaderboard(tmp_path)
    assert df.height == 0
    assert df.columns == ["variant", "passed", "model_version"]


@pytest.mark.unit
def test_leaderboard_broken_yaml_raises_with_filename(tmp_path: Path) -> None:
    """トップが辞書でない yaml → どのファイルかが分かる ValueError。"""
    (tmp_path / "metrics_bad.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="metrics_bad"):
        leaderboard(tmp_path)


@pytest.mark.unit
def test_leaderboard_unknown_sort_by_raises(tmp_path: Path) -> None:
    """sort_by が表に無い指標 → 指標名を含む ValueError（黙って無視しない）。"""
    _write_metrics(tmp_path, "a", {"roc_auc": 0.9})
    with pytest.raises(ValueError, match="accuracy"):
        leaderboard(tmp_path, sort_by="accuracy")


@pytest.mark.integration
def test_cli_experiments_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI（data experiments）を関数直呼び → 例外なく表が出る（exit 0 相当）。"""
    from harness.ds.cli import _data_experiments

    _write_metrics(tmp_path, "a", {"roc_auc": 0.90}, version="va")
    _write_metrics(tmp_path, "b", {"roc_auc": 0.95}, version="vb")
    _data_experiments(results=tmp_path)
    out = capsys.readouterr().out
    assert "variant" in out and "roc_auc" in out
    assert "vb" in out  # model_version も表に出る


@pytest.mark.integration
def test_cli_experiments_empty_dir_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """結果が無いディレクトリ → 落ちずに案内を出す。"""
    from harness.ds.cli import _data_experiments

    _data_experiments(results=tmp_path)
    assert "実験結果が無い" in capsys.readouterr().out


@pytest.mark.unit
def test_leaderboard_mixed_int_float_metric_coerces_not_crash(tmp_path: Path) -> None:
    # 同じ指標が片方 int（yaml で 1）・片方 float（0.5）でも、float に正規化して落ちない（polars TypeError にしない）。
    (tmp_path / "metrics_a.yaml").write_text("variant: a\nmetrics: {m: 1}\n", encoding="utf-8")
    (tmp_path / "metrics_b.yaml").write_text("variant: b\nmetrics: {m: 0.5}\n", encoding="utf-8")
    df = leaderboard(tmp_path)
    assert df["m"].dtype == pl.Float64
    assert df["m"].to_list() == [1.0, 0.5]  # a(1.0) > b(0.5) 降順


@pytest.mark.unit
def test_leaderboard_non_numeric_metric_raises_with_filename(tmp_path: Path) -> None:
    # 数値でない指標値は、どのファイル・どの指標かを含む ValueError（黙って polars エラーにしない）。
    (tmp_path / "metrics_a.yaml").write_text("variant: a\nmetrics: {m: not_a_number}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="metrics_a.yaml.*数値でない"):
        leaderboard(tmp_path)


@pytest.mark.unit
def test_leaderboard_nan_metric_sorts_last(tmp_path: Path) -> None:
    # NaN な指標の変種は優勝に見せない（最下位へ）。良い行が先・NaN は末尾。
    (tmp_path / "metrics_bad.yaml").write_text("variant: bad\nmetrics: {m: .nan}\n", encoding="utf-8")
    (tmp_path / "metrics_good.yaml").write_text("variant: good\nmetrics: {m: 0.5}\n", encoding="utf-8")
    df = leaderboard(tmp_path, sort_by="m")
    assert df["variant"].to_list()[0] == "good"  # NaN の bad は先頭に来ない
    assert df["variant"].to_list()[-1] == "bad"


@pytest.mark.unit
def test_leaderboard_missing_dir_raises(tmp_path: Path) -> None:
    # 存在しないディレクトリは空表と取り違えず ValueError（打ち間違いに気づける）。
    with pytest.raises(ValueError, match="results ディレクトリが無い"):
        leaderboard(tmp_path / "nope")
