"""教師なしの CLI 入口（data cluster/embed/anomaly）が、id を特徴に混ぜないことの回帰テスト。

store のテーブルは必ず id（単調増加の識別子）を持つ。id を数値列として教師なしに食わせると
クラスタ/埋め込み/異常スコアが歪む（リークの温床）。既定で id を外すのを CLI 経路で固定する。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
import yaml

from harness import cli
from harness.ds import store

pytestmark = pytest.mark.integration

_SCHEMA = {
    "id": "points",
    "description": "教師なし用の数値テーブル",
    "layer": "processed",
    "scope": "project",
    "primary_key": ["id"],
    "columns": [
        {"name": "id", "dtype": "Int64", "nullable": False, "unique": True},
        {"name": "x1", "dtype": "Float64", "nullable": False},
        {"name": "x2", "dtype": "Float64", "nullable": False},
        {"name": "x3", "dtype": "Float64", "nullable": False},
    ],
}


def _make_table(make_project: Callable[..., Any]) -> Any:
    proj = make_project()
    proj.add_schema(_SCHEMA)
    rng = np.random.default_rng(0)
    df = pl.DataFrame(
        {
            "id": list(range(40)),
            "x1": [float(i % 2) + float(rng.normal(0, 0.05)) for i in range(40)],  # 2 塊
            "x2": [float((i % 2) * 10) + float(rng.normal(0, 0.05)) for i in range(40)],
            "x3": [float(rng.normal(0, 1.0)) for i in range(40)],
        }
    )
    store.save(proj.root, df, "points")
    return proj


def _run(
    monkeypatch: pytest.MonkeyPatch, root: Path, fn: Callable[..., None], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    monkeypatch.chdir(root)  # _root() は Path.cwd() を返すので作業ディレクトリを移す
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return dict(yaml.safe_load(buf.getvalue()))


def test_cluster_cli_excludes_id_by_default(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    proj = _make_table(make_project)
    out = _run(monkeypatch, proj.root, cli._data_cluster, "points", k=2)
    assert out["columns"] == ["x1", "x2", "x3"]  # id は特徴に入らない
    assert "id" not in out["columns"]


def test_anomaly_cli_excludes_id_by_default(make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    proj = _make_table(make_project)
    out = _run(monkeypatch, proj.root, cli._data_anomaly, "points", top=5)
    assert out["anomaly"]["columns"] == ["x1", "x2", "x3"]  # id を除いた数値列で採点
    top_ids = {r["id"] for r in out["top_rows"]}
    assert top_ids <= set(range(40))  # 上位行は元 df の id を保って出る


def test_embed_cli_excludes_id_and_columns_override(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _make_table(make_project)
    out = _run(monkeypatch, proj.root, cli._data_embed, "points")
    assert out["columns"] == ["x1", "x2", "x3"]
    # --columns で明示すればそれに従う（id を外した既定と違う部分集合を選べる）。
    out2 = _run(monkeypatch, proj.root, cli._data_embed, "points", columns="x1,x3")
    assert out2["columns"] == ["x1", "x3"]
