"""E-0001 の唯一の実行体。データ生成→特徴量→交差検証→合否→保存→results を一気通貫で回す。

**この実験フォルダは以後の実験のコピー元（雛形）**。新しい実験は experiment スキルの手順どおり、これを
丸ごとコピーして config.yaml だけ書き換える（train.py は触らない）。特徴量・エンコーダの kind は
`uv run data blocks` / `uv run data encoders` の一覧から選ぶ。

使い方：`python train.py [--config <yaml>] --variant <config の variants キー> [--test] [--root <dir>] [--out <dir>]`
- 変種は config.yaml の variants 節で持つ（実験＝1 仮説）。各変種は build_estimator の spec（features / encode）。
- task（config の task 節）で評価の後段を分岐する（雛形本体は 1 つ・違いは config で選ぶ）：
  classification（二値・既定）＝OOF で決定境界を選び二値指標／multiclass＝argmax の多クラス指標／
  regression＝予測値の回帰指標（多クラス・回帰に閾値選択は無い）。config は --config で選ぶ
  （既定 config.yaml＝二値。回帰・多クラスの変種は config-regression.yaml / config-multiclass.yaml）。
- --test は小さな規模（config の test_mode）でスモークする。--root 未指定の --test は毎回新しい一時ディレクトリ。
- 特徴量→（エンコード）→モデルは 1 本の sklearn Pipeline を harness.ds.pipeline.build_estimator が config から組む。
  run_experiment が fold ごとに clone→train で fit（漏れ防止は構造）。CV・保存・閾値は再実装しない（部品が正本）。
- fold 表を split 層・OOF を processed 層に store 保存して再現をデータで担保する（核2）。学習器は全データで
  学習し直して丸ごと保存（前処理と本体がワンセット）。乱数は明示引数（seed）だけ・グローバル種は使わない。
- 最終評価：先に `data.fixed_split` で test（holdout）を取り分け、選抜・閾値は残り（df_fit）の全行 OOF で決める。
  確定後に `final_eval_on_holdout` を一度だけ呼んで results に記録する（holdout は選抜・閾値調整に使わない）。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from harness.ds import data, store
from harness.ds import eval as ev
from harness.ds import models as model_store
from harness.ds.experiment import ExperimentSpec, final_eval_on_holdout, run_experiment
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

# ---- 実験ローカルのデータ源（task 変種用） ----
# 共通部品の synthetic（harness.ds.data.generate_synthetic）は二値のみ。回帰・多クラスの config 変種
# （config-regression.yaml / config-multiclass.yaml）用の合成データはこの実験のローカル源として
# DATA_SOURCES に登録し、config の data.kind で選ぶ（データの選択も config＝雛形本体は 1 つ）。
# 2 本目の実験でも要るようになったら src/harness/ds/data.py の DATA_SOURCES へ昇格する。


def _synthetic_regression(root: Path, *, n: int, seed: int, **_ignored: object) -> pl.DataFrame:
    """回帰の合成データ（E-0001 ローカル）。y = 1.5*x1 − 2.0*x2 + 雑音（std 0.5）＝線形で当てられる連続値。"""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 1.5 * x1 - 2.0 * x2 + rng.normal(scale=0.5, size=n)
    return pl.DataFrame({"id": np.arange(n, dtype="int64"), "x1": x1, "x2": x2, "y": y})


def _synthetic_multiclass(root: Path, *, n: int, seed: int, **_ignored: object) -> pl.DataFrame:
    """3 クラスの合成データ（E-0001 ローカル）。線形スコアを ±1.0 で区切り y∈{0,1,2}（cv の 0..k-1 契約）。"""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    score = 1.5 * x1 - 2.0 * x2 + rng.normal(scale=0.5, size=n)
    y = np.digitize(score, [-1.0, 1.0]).astype("int64")  # 3 クラスが各 30〜35% のほぼ均衡になる区切り
    return pl.DataFrame({"id": np.arange(n, dtype="int64"), "x1": x1, "x2": x2, "y": y})


data.DATA_SOURCES.register("synthetic_regression", _synthetic_regression)
data.DATA_SOURCES.register("synthetic_multiclass", _synthetic_multiclass)


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
    # --config を先に読む（--variant の選択肢は config の variants キーから導くため 2 段で解析する）。
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument(
        "--config",
        type=Path,
        default=CONFIG,
        help="実験 config（既定 config.yaml＝二値。task 変種は config-regression.yaml / config-multiclass.yaml）",
    )
    pre_args, _rest = pre.parse_known_args()
    cfg = yaml.safe_load(pre_args.config.read_text(encoding="utf-8"))
    spec = ExperimentSpec.model_validate(cfg)  # 型の正本。未知キー・型違いを起動時に止め、以後は spec から読む
    parser = argparse.ArgumentParser(parents=[pre])
    parser.add_argument("--variant", default=next(iter(spec.variants)), choices=list(spec.variants))
    parser.add_argument("--test", action="store_true", help="小さな規模でスモークする")
    parser.add_argument(
        "--root", type=Path, default=None, help="store の置き場（既定＝リポ根／--test は一時ディレクトリ）"
    )
    parser.add_argument("--out", type=Path, default=None, help="results の書き出し先")
    args = parser.parse_args()

    tm = spec.test_mode
    seed = spec.seed
    n = tm.n if (args.test and tm is not None and tm.n is not None) else spec.n
    n_folds = tm.n_folds if (args.test and tm is not None and tm.n_folds is not None) else spec.n_folds
    variant_spec = cfg["variants"][args.variant]  # build_estimator の spec（features / encode / select）＝検証済み構造
    variant = spec.variants[args.variant]
    thresholds = spec.thresholds
    target = spec.target  # 目的変数の列名（config で選ぶ）
    task = spec.task  # classification / multiclass / regression（モデル種との整合を検査）
    data_spec = spec.data  # 入力源（synthetic / table）
    # モデルは variant 優先→experiment 既定（モデル比較実験は variant に model を書く）。
    model_spec = variant.model or spec.model
    # 層化：分類は既定で目的変数（クラス比を保つ）。config の stratify_by で上書き。order_by・回帰は層化しない。
    if spec.order_by is not None:
        stratify_by = None
    elif spec.stratify_by is not None:
        stratify_by = spec.stratify_by
    else:
        stratify_by = target if task != "regression" else None

    root = prepare_root(test=args.test, root=args.root)
    # --test の既定 out は root 側へ（試走が本物の results/ を上書きしないように）。--out の明示指定は常に優先。
    out = args.out if args.out is not None else (root / "results" if root != ROOT_DEFAULT else HERE.parent / "results")

    df_all = data.load_dataset(root, data_spec, n=n, seed=seed)
    # 最終評価用の test（holdout）を先に取り分ける（id ハッシュの安定分割＝再実行しても同じ行）。
    # 選抜・閾値調整は残り（df）の全行 OOF で行い、holdout は最後の final_eval_on_holdout でだけ触る。
    split = data.fixed_split(df_all, valid_pct=0, test_pct=20)
    df, df_test = split["train"], split["test"]
    y = df[target].to_numpy().astype("float64")
    y_test = df_test[target].to_numpy().astype("float64")
    estimator = build_estimator(variant_spec, build_model(model_spec, seed=seed, task=task), seed=seed)
    result = run_experiment(
        df,
        y,
        estimator,
        n_folds=n_folds,
        seed=seed,
        thresholds=thresholds,
        task=task,
        stratify_by=stratify_by,
        order_by=spec.order_by,
        metrics=spec.metrics,
        id_column=spec.id_column,
    )

    if not result.cv.oof_mask.all():
        raise SystemExit("OOF が全行を覆っていない（この実験は全行 CV 前提。分割を見直すこと）")
    folds_fp = save_folds(root, result.folds)
    # OOF の保存列：二値=陽性確率・回帰=予測値（どちらも (n,) の float）。多クラスの OOF は (n, k) の proba
    # なので予測クラス（argmax・0..k-1）を保存する（1 列の表に収める＝テーブル定義 e0001_oof_* の oof_score）。
    oof_series = (
        pl.Series("oof_score", result.cv.oof.argmax(axis=1).astype("int64"))
        if task == "multiclass"
        else pl.Series("oof_score", result.cv.oof)
    )
    oof_table = (
        df.select("id")
        .with_columns(
            y=df[target],  # 保存する OOF 表の列名は y に揃える（e0001_oof のテーブル定義）
            fold=result.folds["fold"],
            oof_score=oof_series,
        )
        .select("id", "fold", "y", "oof_score")
    )
    oof_fp = store.save(root, oof_table, f"e0001_oof_{args.variant}", code=CODE_REF, work=WORK_ID)

    # task で評価の後段を分岐：binary（classification）だけ OOF で決定境界（閾値）を選ぶ。
    # multiclass は argmax・regression は予測値そのもので評価するので閾値選択は無い
    # （run_experiment・final_eval_on_holdout の対応経路が指標を切り替える）。
    threshold_block: dict[str, object] | None = None
    metrics_at: dict[str, float] | None = None
    decision_threshold = 0.5  # 二値以外では使われない（final_eval_on_holdout の既定と同じ）
    if task == "classification":
        y_int = df[target].to_numpy().astype("int64")
        threshold, f1_at = ev.select_threshold_max_f1(y_int, result.cv.oof)  # 閾値は OOF で選ぶ（規約）
        metrics_at = ev.evaluate(y_int, result.cv.oof, threshold=threshold)
        threshold_block = {"method": "max_f1", "value": threshold, "f1": f1_at}
        decision_threshold = threshold

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

    # 最終評価：OOF で選抜・閾値決定を終えた後、触っていない test（holdout）で一度だけ測る（選抜には使わない）。
    holdout = final_eval_on_holdout(
        estimator,
        df,
        y,
        df_test,
        y_test,
        task=task,
        decision_threshold=decision_threshold,
        thresholds=thresholds,
        metrics=spec.metrics,
        id_column=spec.id_column,
    )

    payload: dict[str, object] = {
        "variant": args.variant,
        "mode": "test" if args.test else "full",
        "seed": seed,
        "n": n,
        "n_folds": n_folds,
        "task": task,
        "metrics": result.metrics,
        "passed": result.passed,
    }
    if threshold_block is not None:  # 二値だけ（多クラス・回帰の results に決定境界の欄は無い）
        payload["threshold"] = threshold_block
        payload["metrics_at_threshold"] = metrics_at
    payload.update(
        {
            "holdout": {"n": df_test.height, "metrics": holdout.metrics, "passed": holdout.passed},
            "fingerprints": {"folds": folds_fp, "oof": oof_fp, "model": record.fingerprint},
            "model": {"name": record.name, "version": record.version},
            "feature_names": list(record.feature_names),
        }
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / f"metrics_{args.variant}.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"variant={args.variant} passed={result.passed} metrics={result.metrics}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
