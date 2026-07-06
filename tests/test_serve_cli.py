"""serve CLI（uvicorn 起動の入口）と軽 import のテスト。実サーバ・実ネットワークは使わない。

- uvicorn.run は monkeypatch で捕まえ、渡る引数（app・host・port）だけを検査する。
- extra 未導入（fastapi/uvicorn 不在）は sys.modules に None を差して再現し、案内＋exit 1 を検査する。
- 軽 import は subprocess の素の Python で `import harness.serve` し、fastapi/uvicorn が読み込まれない
  ことを固定する（プロファイルのモジュールは重い依存を top で import しない規約＝DEC-0013）。
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import typer

pytestmark = pytest.mark.integration


def _promoted_champion(root: Path) -> None:
    """champion 1 版の最小構成（x1/x2 の二値分類）。"""
    pytest.importorskip("fastapi")  # optional extra `serve`（ISS ではない）
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    from harness.ds import data
    from harness.ds import models as model_store
    from harness.ds.features import Columns, FeaturePipeline

    df = data.generate_synthetic(n=60, seed=0)
    est = Pipeline(
        [
            ("features", FeaturePipeline([("columns", Columns(["x1", "x2"]))])),
            ("model", LogisticRegression(random_state=0, max_iter=1000)),
        ]
    )
    est.fit(df, df["y"].to_numpy().astype(np.float64))
    record = model_store.save_model(root, est, name="baseline", work="E-0001", metrics={"rmse": 0.5})
    model_store.promote_model(
        root, work="E-0001", name="baseline", version=record.version, thresholds={"rmse": 1.0}, primary="rmse"
    )


def test_serve_cli_passes_app_and_host_port_to_uvicorn(
    make_project: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    fastapi = pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    proj = make_project()
    _promoted_champion(proj.root)

    captured: dict[str, Any] = {}

    def fake_run(app: Any, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", fake_run)  # 実サーバは起動しない
    from harness.serve.cli import _serve

    _serve(work="E-0001", name="baseline", host="127.0.0.1", port=9000, root=proj.root)
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9000
    assert isinstance(captured["app"], fastapi.FastAPI)  # create_app の結果がそのまま uvicorn に渡る
    assert captured["app"].state.record.name == "baseline"  # champion が載っている


def test_serve_cli_without_serve_extra_guides_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # sys.modules[名前] = None は「その import を ImportError にする」標準の再現方法（uv sync 無しで再現）。
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    from harness.serve.cli import _serve

    with pytest.raises(typer.Exit) as exc_info:
        _serve(work="E-0001", name="baseline")
    assert exc_info.value.exit_code == 1
    assert "uv sync --extra serve" in capsys.readouterr().out  # 導入方法を案内する（生の栈を吐かない）


def test_import_harness_serve_stays_light() -> None:
    # 素の Python で import harness.serve しても fastapi/uvicorn は読み込まれない（PROFILE 経路の軽さを固定）。
    code = (
        "import sys\n"
        "import harness.serve\n"
        "assert harness.serve.PROFILE.name == 'serve', harness.serve.PROFILE\n"
        "assert harness.serve.PROFILE.pm_checks == (), harness.serve.PROFILE\n"
        "heavy = [m for m in ('fastapi', 'uvicorn') if m in sys.modules]\n"
        "assert not heavy, f'import harness.serve が重い依存を読み込んだ: {heavy}'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
