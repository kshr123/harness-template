"""E-0001 の唯一の実行体。データ生成→特徴量→交差検証→合否→results を一気通貫で回す。

使い方：`python train.py --variant baseline|interaction [--test] [--out <dir>]`
- 変種は config.yaml の features 節で持つ（実験＝1 仮説）。
- --test は小さな規模（config の test_mode）でスモークする。--out は results の書き出し先。
- 特徴量→モデルは 1 本の sklearn Pipeline。run_experiment が fold ごとに clone→train で fit する
  （漏れ防止は構造）。乱数は明示引数（seed）だけで、グローバル種は使わない。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from harness.ds import data
from harness.ds.experiment import run_experiment
from harness.ds.features import Columns, FeaturePipeline, Interactions

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config.yaml"


def build_estimator(feature_spec: list[str], seed: int) -> Pipeline:
    """config の features 指定から、特徴量→モデルの 1 本の Pipeline を組む。"""
    blocks: list[tuple[str, object]] = []
    if "columns" in feature_spec:
        blocks.append(("columns", Columns(["x1", "x2"])))
    if "interaction" in feature_spec:
        blocks.append(("interaction", Interactions([("x1", "x2")])))
    return Pipeline(
        [
            ("features", FeaturePipeline(blocks)),
            ("model", LogisticRegression(random_state=seed, max_iter=1000)),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="baseline", choices=["baseline", "interaction"])
    parser.add_argument("--test", action="store_true", help="小さな規模でスモークする")
    parser.add_argument("--out", type=Path, default=HERE.parent / "results", help="results の書き出し先")
    args = parser.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    seed = int(cfg["seed"])
    n = int(cfg["test_mode"]["n"] if args.test else cfg["n"])
    n_folds = int(cfg["test_mode"]["n_folds"] if args.test else cfg["n_folds"])
    feature_spec = cfg["variants"][args.variant]["features"]
    thresholds = cfg["thresholds"]

    df = data.generate_synthetic(n=n, seed=seed)
    y = df["y"].to_numpy().astype("float64")
    estimator = build_estimator(feature_spec, seed)
    result = run_experiment(df, y, estimator, n_folds=n_folds, seed=seed, thresholds=thresholds, stratify_by="y")

    args.out.mkdir(parents=True, exist_ok=True)
    record = {
        "variant": args.variant,
        "metrics": result.metrics,
        "passed": result.passed,
        "seed": seed,
        "n": n,
        "n_folds": n_folds,
    }
    (args.out / f"metrics_{args.variant}.yaml").write_text(
        yaml.safe_dump(record, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"variant={args.variant} passed={result.passed} metrics={result.metrics}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
