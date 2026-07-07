"""E-0001 の端から端まで（e2e）スモーク。実験スクリプトそのものを subprocess で叩く。

これにより「雛形から乖離した実験」「テストだけ通る二重実装」が構造的に不可能になる——
verify（full で e2e が走る）が落ちるのは実験スクリプト本体が壊れたとき。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest
import yaml

pytestmark = pytest.mark.e2e

_ROOT = Path(__file__).resolve().parents[1]  # harness-template リポの根
_EXPERIMENT = _ROOT / "templates" / "experiment"  # 実験雛形の正本（T-0140 で work/E-0001 から移設）
_TRAIN = _EXPERIMENT / "train.py"


def _run(tmp_path: Path, variant: str, *, config: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONUTF8": "1"}  # Windows コンソールでも日本語・記号を出せるように
    cmd = [sys.executable, str(_TRAIN), "--variant", variant, "--test", "--root", str(tmp_path)]
    if config is not None:  # 雛形本体は 1 つ・task 変種は config ファイルで選ぶ（既定は config.yaml＝二値）
        cmd += ["--config", str(config)]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
    )


def test_e0001_smoke(tmp_path: Path) -> None:
    result = _run(tmp_path, "baseline")
    assert result.returncode == 0, result.stderr  # 端から端まで通って合否（0=閾値を満たす）
    metrics = tmp_path / "results" / "metrics_baseline.yaml"
    assert metrics.is_file()  # results が書き出される
    record = yaml.safe_load(metrics.read_text(encoding="utf-8"))
    assert record["fingerprints"]["folds"] and record["fingerprints"]["model"]  # 保存の指紋が結ばれる
    # fold 表（split 層）とモデルの manifest が実体として保存される。
    assert (tmp_path / "data" / "work" / "E-0001" / "split" / "e0001_folds.parquet").is_file()
    assert list((tmp_path / "data" / "work" / "E-0001" / "models" / "baseline").glob("*/manifest.yaml"))


def test_e0001_two_variants_share_folds(tmp_path: Path) -> None:
    # 同じ root で baseline→interaction を続けて実行＝同一分割で比較（核2の実地）。両 results の fold 指紋が一致。
    assert _run(tmp_path, "baseline").returncode == 0
    assert _run(tmp_path, "interaction").returncode == 0
    base = yaml.safe_load((tmp_path / "results" / "metrics_baseline.yaml").read_text(encoding="utf-8"))
    inter = yaml.safe_load((tmp_path / "results" / "metrics_interaction.yaml").read_text(encoding="utf-8"))
    assert base["fingerprints"]["folds"] == inter["fingerprints"]["folds"]  # 同一分割で比較した証拠


def test_e0001_regression_smoke(tmp_path: Path) -> None:
    # 雛形は 1 つ（train.py）・task は config で選ぶ：回帰 config の --test スモークが端から端まで通る。
    result = _run(tmp_path, "reg_baseline", config=_EXPERIMENT / "config-regression.yaml")
    assert result.returncode == 0, result.stderr
    record = yaml.safe_load((tmp_path / "results" / "metrics_reg_baseline.yaml").read_text(encoding="utf-8"))
    assert record["task"] == "regression"
    # 期待値はデータ構成から導く：y = 1.5*x1 − 2.0*x2 + 雑音(std 0.5)。線形モデル（ridge）は係数を回復できる
    # ので残差 ≈ 雑音 → OOF rmse ≈ 0.5（CV・有限標本の揺れを見て 0.6 以下）。
    # var(y) = 1.5² + 2² + 0.5² = 6.5 → r2 ≈ 1 − 0.25/6.5 ≈ 0.96（余裕を見て 0.9 以上）。
    assert record["metrics"]["rmse"] <= 0.6
    assert record["metrics"]["r2"] >= 0.9
    assert "threshold" not in record  # 回帰に決定境界（閾値選択）は無い＝二値だけの後段
    assert "metrics_at_threshold" not in record
    assert "rmse" in record["holdout"]["metrics"]  # holdout も回帰指標で測られる
    assert record["fingerprints"]["folds"] and record["fingerprints"]["model"]  # 保存の指紋が結ばれる


def test_e0001_multiclass_smoke(tmp_path: Path) -> None:
    # 多クラス config の --test スモーク：OOF は (n, k) の proba・評価は argmax（閾値選択は無い）。
    result = _run(tmp_path, "mc_baseline", config=_EXPERIMENT / "config-multiclass.yaml")
    assert result.returncode == 0, result.stderr
    record = yaml.safe_load((tmp_path / "results" / "metrics_mc_baseline.yaml").read_text(encoding="utf-8"))
    assert record["task"] == "multiclass"
    # 期待値はデータ構成から導く：線形スコア 1.5*x1 − 2.0*x2 + 雑音(std 0.5)（sd ≈ √6.5 ≈ 2.55）を ±1.0 で
    # 3 分割 → 各クラス約 30〜35%（偶然の正解率 ≈ 0.35）。ラベルの取り違えは境界近傍の雑音だけ
    # （flip 率 ≈ 0.12 → 正解率の上限 ≈ 0.88）なので、線形境界を引ける logreg は 0.7 を余裕で超える。
    assert record["metrics"]["accuracy"] >= 0.7
    assert record["metrics"]["macro_f1"] >= 0.7  # クラスがほぼ均衡なので macro_f1 も accuracy に追随する
    assert "threshold" not in record  # 多クラスは argmax（二値の閾値選択は無い）
    assert "metrics_at_threshold" not in record
    assert "macro_f1" in record["holdout"]["metrics"]  # holdout も多クラス指標で測られる
    # OOF の保存は予測クラス（argmax）。各クラス 3 割前後の構成なので 3 クラスすべて予測に現れる。
    oof = pl.read_parquet(tmp_path / "data" / "work" / "E-0001" / "processed" / "e0001_oof_mc_baseline.parquet")
    assert set(oof["oof_score"].unique().to_list()) == {0, 1, 2}
