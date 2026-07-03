"""E-0001 の唯一の実行体。データ生成→特徴量→交差検証→合否→保存→results を一気通貫で回す。

**この実験フォルダは以後の実験のコピー元（雛形）**。新しい実験は experiment スキルの手順どおり、これを
丸ごとコピーして config.yaml だけ書き換える（train.py は触らない）。特徴量・エンコーダの kind は
`uv run data blocks` / `uv run data encoders` の一覧から選ぶ。

使い方：`python train.py --variant <config の variants キー> [--test] [--root <dir>] [--out <dir>]`
- 変種は config.yaml の variants 節で持つ（実験＝1 仮説）。各変種は build_estimator の spec（features / encode）。
- --test は小さな規模（config の test_mode）でスモークする。--root 未指定の --test は毎回新しい一時ディレクトリ。
- 特徴量→（エンコード）→モデルは 1 本の sklearn Pipeline を harness.ds.pipeline.build_estimator が config から組む。
  run_experiment が fold ごとに clone→train で fit（漏れ防止は構造）。CV・保存・閾値は再実装しない（部品が正本）。
- fold 表を split 層・OOF を processed 層に store 保存して再現をデータで担保する（核2）。学習器は全データで
  学習し直して丸ごと保存（前処理と本体がワンセット）。乱数は明示引数（seed）だけ・グローバル種は使わない。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import polars as pl
import yaml

from harness.ds import data, store
from harness.ds import eval as ev
from harness.ds import models as model_store
from harness.ds.experiment import run_experiment
from harness.ds.pipeline import build_estimator, build_model

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config.yaml"
ROOT_DEFAULT = HERE.parents[3]  # code → E-0001 → EP-06 → work → リポ根
WORK_ID = "E-0001"
CODE_REF = "work/EP-06-ds-experiment-loop/E-0001-interaction-feature/code/train.py"

# conftest.DEFAULT_CONFIG と同文（config.py の既定と同じ形。tests から import しない＝依存を逆流させない）。
DEFAULT_CONFIG = """\
[data]
default_backend = "local"

[data.backends.local]
uri = "file:data"

[data.layer]

[issues]
backend = "file:issues"

[metadata]
uri = "file:docs/data"
"""


def prepare_root(*, test: bool, root: Path | None) -> Path:
    """store が要る前提（config.toml・テーブル定義）を root に整える。

    - 本規模（--test なし・--root なし）＝リポ根。組み立て不要（config も定義も実在）。
    - --test で --root なし＝毎回新しい一時ディレクトリ（split 再保存拒否と何度でも実行が両立）。
    - --root 指定（e2e の tmp 等）＝そこに無いものだけ組み立てる（再実行できる）。
    """
    if root is None:
        if not test:
            return ROOT_DEFAULT
        root = Path(tempfile.mkdtemp(prefix="e0001-"))
    if root != ROOT_DEFAULT:
        cfg = root / ".harness" / "config.toml"
        if not cfg.is_file():
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(DEFAULT_CONFIG, encoding="utf-8")
        ddir = root / "work" / WORK_ID / "data"
        ddir.mkdir(parents=True, exist_ok=True)
        for src in (HERE.parent / "data").glob("*.yaml"):
            shutil.copy(src, ddir / src.name)  # 定義は正本のコピー（内容同一なので上書き可）
    return root


def save_folds(root: Path, folds: pl.DataFrame) -> str:
    """fold 表を split 層に保存し指紋を返す。保存済みなら同一性を確かめて既存の指紋を返す

    （＝2 変種目・再実行。同じ seed なら make_folds は同じ表になる前提で、違えば止める）。
    """
    existing = store.fingerprint_of(root, "e0001_folds")
    if existing is None:
        return store.save(root, folds, "e0001_folds", code=CODE_REF, work=WORK_ID)
    saved = store.load(root, "e0001_folds").sort("id")
    if not saved.equals(folds.sort("id")):
        raise SystemExit("保存済みの fold 表と一致しない（seed を変えたなら root を変える。分割は切り直さない）")
    return existing


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))  # --variant の選択肢は config の variants キーから導く
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default=next(iter(cfg["variants"])), choices=list(cfg["variants"]))
    parser.add_argument("--test", action="store_true", help="小さな規模でスモークする")
    parser.add_argument(
        "--root", type=Path, default=None, help="store の置き場（既定＝リポ根／--test は一時ディレクトリ）"
    )
    parser.add_argument("--out", type=Path, default=None, help="results の書き出し先")
    args = parser.parse_args()

    seed = int(cfg["seed"])
    n = int(cfg["test_mode"]["n"] if args.test else cfg["n"])
    n_folds = int(cfg["test_mode"]["n_folds"] if args.test else cfg["n_folds"])
    variant_spec = cfg["variants"][args.variant]  # build_estimator の spec（features / encode）
    thresholds = cfg["thresholds"]
    target = cfg.get("target", "y")  # 目的変数の列名（config で選ぶ）
    data_spec = cfg.get("data", {"kind": "synthetic"})  # 入力源（synthetic / table）
    # モデルは variant 優先→experiment 既定→logreg（モデル比較実験は variant に model を書く）。
    model_spec = variant_spec.get("model") or cfg.get("model") or {"kind": "logreg"}

    root = prepare_root(test=args.test, root=args.root)
    # --test の既定 out は root 側へ（試走が本物の results/ を上書きしないように）。--out の明示指定は常に優先。
    out = args.out if args.out is not None else (root / "results" if root != ROOT_DEFAULT else HERE.parent / "results")

    df = data.load_dataset(root, data_spec, n=n, seed=seed)
    y = df[target].to_numpy().astype("float64")
    estimator = build_estimator(variant_spec, build_model(model_spec, seed=seed), seed=seed)
    result = run_experiment(df, y, estimator, n_folds=n_folds, seed=seed, thresholds=thresholds, stratify_by=target)

    if not result.cv.oof_mask.all():
        raise SystemExit("OOF が全行を覆っていない（この実験は全行 CV 前提。分割を見直すこと）")
    folds_fp = save_folds(root, result.folds)
    oof_table = (
        df.select("id")
        .with_columns(
            y=df[target],  # 保存する OOF 表の列名は y に揃える（e0001_oof のテーブル定義）
            fold=result.folds["fold"],
            oof_score=pl.Series("oof_score", result.cv.oof),
        )
        .select("id", "fold", "y", "oof_score")
    )
    oof_fp = store.save(root, oof_table, f"e0001_oof_{args.variant}", code=CODE_REF, work=WORK_ID)

    y_int = df[target].to_numpy().astype("int64")
    threshold, f1_at = ev.select_threshold_max_f1(y_int, result.cv.oof)  # 閾値は OOF で選ぶ（規約）
    metrics_at = ev.evaluate(y_int, result.cv.oof, threshold=threshold)

    estimator.fit(df, y)  # 配布用は全データで学習し直す（run_cv は clone するので estimator は未学習のまま）
    record = model_store.save_model(
        root,
        estimator,
        name=args.variant,
        work=WORK_ID,
        data_fingerprint=folds_fp,
        config={
            "variant": args.variant,
            "seed": seed,
            "n": n,
            "n_folds": n_folds,
            "spec": variant_spec,
            "model": model_spec,
            "data": data_spec,
        },
        metrics=result.metrics,
    )

    out.mkdir(parents=True, exist_ok=True)
    (out / f"metrics_{args.variant}.yaml").write_text(
        yaml.safe_dump(
            {
                "variant": args.variant,
                "mode": "test" if args.test else "full",
                "seed": seed,
                "n": n,
                "n_folds": n_folds,
                "metrics": result.metrics,
                "passed": result.passed,
                "threshold": {"method": "max_f1", "value": threshold, "f1": f1_at},
                "metrics_at_threshold": metrics_at,
                "fingerprints": {"folds": folds_fp, "oof": oof_fp, "model": record.fingerprint},
                "model": {"name": record.name, "version": record.version},
                "feature_names": list(record.feature_names),
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"variant={args.variant} passed={result.passed} metrics={result.metrics}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
