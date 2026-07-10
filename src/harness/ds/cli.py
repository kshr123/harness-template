"""DS プロファイルの CLI 入口（typer）。`uv run data <サブコマンド>` で呼ぶ。

中核の CLI（src/harness/cli.py＝status/verify 等）とは分ける（プロファイル境界）。
重い依存（polars・sklearn）は各コマンドの中で遅延取り込みする（一覧系を軽く保つ）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

# render_catalog は harness/registry.py へ引き上げた（agent CLI と共用・二重管理を作らない）。
from harness.registry import render_catalog

# Windows コンソール（cp932）でも日本語・記号（✓✗✅）を出せるよう UTF-8 に固定。
# クロスプラットフォームの前提（make 非依存と同じ理由）。
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _root() -> Path:
    return Path.cwd()


data_app = typer.Typer(help="テーブル定義（データのメタデータ）", add_completion=False)


@data_app.command("lint")
def _data_lint() -> None:
    """テーブル定義の静的検査（ID重複・型名・系譜・越境参照）。verify にも含まれる。"""
    from harness.ds import schema

    errors = 0
    for p in schema.data_lint(_root()):
        typer.echo(f"{'✗' if p.level == 'error' else '・'} {p.message}")
        errors += 1 if p.level == "error" else 0
    if errors:
        typer.echo(f"問題 {errors} 件（失敗）")
        raise typer.Exit(1)
    typer.echo("テーブル定義：問題なし")


@data_app.command("list")
def _data_list() -> None:
    """テーブル定義を scope→role でグループ表示する（生成ビュー）。"""
    from harness.ds import schema

    schemas = schema.load_schemas(_root())
    for scope in sorted({s.scope for s in schemas}):
        typer.echo(f"[scope: {scope}]")
        for s in sorted((x for x in schemas if x.scope == scope), key=lambda x: (x.role or "", x.id)):
            typer.echo(f"  {s.layer.value}\t{s.role or '-'}\t{s.id}\t{s.description}")


@data_app.command("blocks")
def _data_blocks() -> None:
    """特徴量ブロックの一覧（BLOCKS レジストリから生成）。config の features 節に書ける kind。"""
    from harness.ds.features import BLOCKS

    render_catalog(BLOCKS, show_params=True)
    typer.echo("\n使い方は experiment / features スキル。無いものは （sklearn が十分なら data encoders を見る）。")


@data_app.command("encoders")
def _data_encoders() -> None:
    """sklearn エンコーダの一覧（ENCODERS レジストリから生成）。config の encode 節に書ける kind。"""
    from harness.ds.pipeline import ENCODERS

    render_catalog(ENCODERS)
    typer.echo("\nparams は sklearn 本体へ素通し（安全既定だけ焼き込み済み）。対象列は encode 項目の columns で指定。")


@data_app.command("models")
def _data_models() -> None:
    """モデル種の一覧（MODELS レジストリから生成）。config の model 節に書ける kind と task。"""
    from harness.ds.forecast import TS_MODELS
    from harness.ds.pipeline import MODELS

    render_catalog(MODELS, show_task=True)
    render_catalog(TS_MODELS, show_task=True)  # statsmodels 導入時のみ。sklearn 背骨に載らない別経路。
    typer.echo(
        "\nparams は本体へ素通し（目的関数も loss/criterion/objective で変える・各 docstring 参照）。"
        "\n[timeseries] は run_forecast 用（sklearn Pipeline には載らない）。未表示なら `uv sync --extra statsmodels`。"
        "\n学習済みモデル（保存版）の一覧は `uv run data saved`。"
    )


@data_app.command("sources")
def _data_sources() -> None:
    """データ源の一覧（DATA_SOURCES レジストリから生成）。config の data 節に書ける kind。"""
    from harness.ds.data import DATA_SOURCES

    render_catalog(DATA_SOURCES)
    typer.echo("\ntable 一覧は `uv run data list`。実データを足すときは ds/data.py の DATA_SOURCES に 1 行。")


@data_app.command("selectors")
def _data_selectors() -> None:
    """特徴選択の一覧（SELECTORS レジストリから生成）。config の select 節に書ける kind。"""
    from harness.ds.pipeline import SELECTORS

    render_catalog(SELECTORS)
    typer.echo("\nselect は to_numpy と model の間の 1 段（run_cv の clone-per-fold で train のみ選択＝リークなし）。")


@data_app.command("tuners")
def _data_tuners() -> None:
    """ハイパラ探索の一覧（TUNERS レジストリから生成）。config の model 節の tune: に書ける kind。"""
    from harness.ds.tune import TUNERS

    render_catalog(TUNERS)
    typer.echo("\nmodel 節に tune: を足すと *SearchCV で包む（run_cv でそのまま nested CV）。optuna は optional。")


@data_app.command("profile")
def _data_profile(
    table_id: str,
    target: Annotated[str | None, typer.Option(help="目的変数の列名（付けると分布の要約も出す）")] = None,
    task: Annotated[str, typer.Option(help="classification | regression")] = "classification",
    seed: Annotated[int, typer.Option(help="mutual_information・leakage_scan の乱数種（--target 時のみ使う）")] = 0,
) -> None:
    """テーブルの構造化レポートを YAML で出す（store 経由＝検証済みテーブルだけを見る）。"""
    import yaml

    from harness.ds import eda, store

    df = store.load(_root(), table_id)
    report: dict[str, object] = {
        "table": table_id,
        "profile": eda.profile(df).to_dict(),
        "missing_patterns": eda.missing_patterns(df).to_dicts(),
        "duplicate_columns": eda.duplicate_columns(df).to_dicts(),
        "high_correlation_pairs": eda.high_correlation_pairs(df).to_dicts(),  # リーク/多重共線の疑い
    }
    if target is not None:
        if task not in ("classification", "regression"):
            typer.echo("task は classification / regression のいずれか")
            raise typer.Exit(1)
        report["target"] = eda.target_summary(df, target=target, task=task)  # type: ignore[arg-type]
        report["category_target"] = eda.category_target_summary(df, target=target).to_dicts()
        report["correlations"] = eda.correlations(df, target=target).to_dicts()  # 目的変数との相関（|r| 降順）
        # 非線形依存（MI 降順・単位はナット）と、リーク疑いの列（column/reason/detail・0 行＝疑いなし）。
        mi = eda.mutual_information(df, target=target, task=task, seed=seed)  # type: ignore[arg-type]
        leakage = eda.leakage_scan(df, target=target, task=task, seed=seed)  # type: ignore[arg-type]
        report["mutual_information"] = mi.to_dicts()
        report["leakage"] = leakage.to_dicts()
    typer.echo(yaml.safe_dump(report, allow_unicode=True, sort_keys=False))


@data_app.command("compare")
def _data_compare(
    train_id: str,
    test_id: str,
    auc: Annotated[bool, typer.Option("--auc", help="分布差 AUC（adversarial validation）も出す")] = False,
    seed: Annotated[int, typer.Option(help="--auc の乱数種")] = 0,
) -> None:
    """train/test の分布比較を YAML で出す（統計・カテゴリ差・PSI。--auc で分布差 AUC も）。store 経由。"""
    import yaml

    from harness.ds import eda, store

    train = store.load(_root(), train_id)
    test = store.load(_root(), test_id)
    report: dict[str, object] = {"train": train_id, "test": test_id, "compare": eda.compare(train, test).to_dict()}
    if auc:
        # 数値の共通列だけで見分ける（既定 spec は数値向け・カテゴリは spec を書いて呼ぶ）。
        # id（行の鍵）は分布差の特徴に入れない：train/test で id 域が分かれると擬似的な完全分離器になり AUC を誤らせる。
        import polars.selectors as cs

        num = [c for c in train.select(cs.numeric()).columns if c in test.columns and c != "id"]
        drift = eda.drift_auc(train, test, columns=num, seed=seed)
        report["drift"] = {"auc": drift.auc, "fold_aucs": drift.fold_aucs, "columns": num}
    typer.echo(yaml.safe_dump(report, allow_unicode=True, sort_keys=False))


@data_app.command("monitor")
def _data_monitor(
    baseline: Annotated[str, typer.Option("--baseline", help="学習基準テーブルの id（store 経由で読む）")],
    log: Annotated[
        str, typer.Option("--log", help="配信予測ログの glob（root 相対）")
    ] = "artifacts/serve/predictions/**/*.jsonl",
    columns: Annotated[
        str | None, typer.Option("--columns", help="対象列（カンマ区切り。省略時は共通列すべて）")
    ] = None,
    auc: Annotated[bool, typer.Option("--auc", help="分布差 AUC（adversarial validation）も出す")] = False,
    since: Annotated[
        str | None, typer.Option("--since", help="この日付（YYYY-MM-DD・境界日を含む）以降の行だけ")
    ] = None,
    role: Annotated[
        str,
        typer.Option("--role", help="集計する役割（primary | shadow | all）。既定 primary＝shadow 行を除外"),
    ] = "primary",
    file_issue: Annotated[
        bool,
        typer.Option("--file-issue", help="band=大変化（PSI_ALERT 以上）の列があれば issues に冪等起票（exit 0）"),
    ] = False,
    seed: Annotated[int, typer.Option(help="--auc の乱数種")] = 0,
) -> None:
    """配信ログ（予測 JSONL）×学習基準テーブルの分布監視表を YAML で出す（psi/band・--auc で drift・予測の要約）。

    門番にしない（分布ずれは exit code に載せず band で人が読む・exit 0。--file-issue の起票も副作用であって
    exit code に載せない）。基準テーブルが読めないときだけ非 0。--role は既定 primary＝shadow 配信
    （docs/serve.md）の並走行を二重計上しない従来相当の集計（role キーが無い旧ログ行は primary 扱い）。
    ログの glob は root 相対（既定 artifacts/serve/predictions/**/*.jsonl）。serve は起動しない（結合は契約のみ）。
    """
    from datetime import date

    import yaml

    from harness.ds import monitor as monitor_mod
    from harness.ds import store

    since_date: date | None = None
    if since is not None:
        try:
            since_date = date.fromisoformat(since)
        except ValueError as exc:
            raise typer.BadParameter(f"--since は YYYY-MM-DD 形式（受領: {since!r}）") from exc
    if role not in ("primary", "shadow", "all"):
        raise typer.BadParameter(f"--role は primary / shadow / all のいずれか（受領: {role!r}）")

    root = _root()
    baseline_df = store.load(root, baseline)  # 読めなければここで例外＝非 0（唯一の門番）
    files = sorted(root.glob(log))
    served = monitor_mod.read_prediction_logs(files, since=since_date, role=role)
    cols = columns.split(",") if columns else None
    report = monitor_mod.monitor(baseline_df, served, columns=cols, auc=auc, seed=seed)
    out: dict[str, object] = {"baseline": baseline, "log": log, **report.to_dict()}
    typer.echo(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
    if file_issue:
        _file_drift_issue(root, baseline=baseline, log=log, psi_rows=report.psi.to_dicts())


def _file_drift_issue(root: Path, *, baseline: str, log: str, psi_rows: list[dict[str, Any]]) -> None:
    """band=大変化（psi >= PSI_ALERT）の列があれば issues backend へ冪等に起票する（`--file-issue` の中身）。

    門番にしない：起票は副作用で exit code に載せない（alert でも・起票済みでも・github: backend でも
    そのまま戻る＝exit 0）。冪等判定は課題本文の「監視指紋」（drift_issue_content の fingerprint）を
    open / in-progress の課題と照合する。起票は issues.py の既存 API（local_dir・next_id）だけを使う
    （backend 分岐を新設しない。github: では `issue new` と同様に GitHub 側で起票する）。
    """
    from datetime import date

    import yaml

    from harness import issues
    from harness.ds import monitor as monitor_mod

    alerts = [r for r in psi_rows if float(r["psi"]) >= monitor_mod.PSI_ALERT]
    if not alerts:
        return  # alert 無し＝起票なし（1 行も出さない）
    content = monitor_mod.drift_issue_content(baseline=baseline, log=log, alerts=alerts, today=date.today())
    for li in issues.load_issues(root):
        if li.issue.state in (issues.IssueState.open, issues.IssueState.in_progress) and content.fingerprint in li.body:
            typer.echo(f"起票済み: {li.issue.id}（同じドリフト内容の課題が未解決＝重複起票しない）")
            return
    directory = issues.local_dir(root)
    if directory is None:
        typer.echo("起票先が github: backend（起票は GitHub 側で行う・監視は継続）")
        return
    directory.mkdir(parents=True, exist_ok=True)
    iid = issues.next_id(root)
    meta: dict[str, Any] = {
        "id": iid,
        "kind": issues.IssueKind.risk.value,
        "state": issues.IssueState.open.value,
        "created": date.today(),
        "found_in": "data monitor --file-issue",
        "title": content.title,
    }
    path = directory / f"{iid}.md"
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{front}---\n# {iid} {content.title}\n\n{content.body}", encoding="utf-8")
    typer.echo(f"起票: {iid}（{path.relative_to(root)}）")


def _feature_columns(df: Any, columns: str | None) -> list[str]:  # noqa: ANN401  polars.DataFrame
    """教師なしに渡す数値列を決める。--columns 指定があればそれ、無ければ数値列から id を除く。

    id（行の鍵・単調増加）は特徴でなく識別子なので既定で外す（data compare と同じ扱い・リークの温床）。
    目的変数を持つ表では --columns で特徴だけに絞る（どの列が目的変数かは表からは分からないため既定では残す）。
    """
    import polars.selectors as cs

    if columns:
        return columns.split(",")
    return [c for c in df.select(cs.numeric()).columns if c != "id"]


@data_app.command("unsupervised")
def _data_unsupervised() -> None:
    """教師なし（次元圧縮・クラスタ・異常検知）のカタログ。3 レジストリから生成し data embed/cluster/anomaly で使う。"""
    from harness.ds.unsupervised import ANOMALY, CLUSTERERS, DIMRED

    for group, registry in (("dimred", DIMRED), ("cluster", CLUSTERERS), ("anomaly", ANOMALY)):
        render_catalog(registry, prefix=group)
    typer.echo("\n埋め込み＝`data embed <表>`／クラスタ＝`data cluster <表> --k N`／異常＝`data anomaly <表>`。")


@data_app.command("cluster")
def _data_cluster(
    table_id: str,
    k: Annotated[
        int | None, typer.Option("--k", help="クラスタ数（kmeans=n_clusters・gmm=n_components。hdbscan は不要）")
    ] = None,
    method: Annotated[str, typer.Option(help="kmeans / gmm / hdbscan")] = "kmeans",
    columns: Annotated[str | None, typer.Option(help="対象列（カンマ区切り。省略時は数値列から id を除く）")] = None,
    scan: Annotated[
        str | None, typer.Option(help="k を振る範囲 lo:hi（例 2:10）。目安の表を併記（kmeans/gmm のみ）")
    ] = None,
    seed: Annotated[int, typer.Option(help="乱数種")] = 0,
) -> None:
    """テーブルをクラスタリングし、構造化レポート（大きさ・シルエット・クラスタ別の数表）を YAML で出す。"""
    import yaml

    from harness.ds import store, unsupervised

    df = store.load(_root(), table_id)
    cols = _feature_columns(df, columns)
    params: dict[str, Any] = {}
    if method in unsupervised.PARAM_FOR_K:
        if k is None:
            raise typer.BadParameter(f"method '{method}' は --k が必要")
        params[unsupervised.PARAM_FOR_K[method]] = k
    report = unsupervised.cluster_summary(df, columns=cols, method=method, seed=seed, **params)
    out: dict[str, object] = {"table": table_id, "method": method, "columns": cols, "cluster": report.to_dict()}
    if scan is not None:
        lo_s, hi_s = scan.split(":")
        table = unsupervised.k_scan(
            df, columns=cols, method=method, k_values=range(int(lo_s), int(hi_s) + 1), seed=seed
        )
        out["scan"] = table.to_dicts()
    typer.echo(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))


@data_app.command("embed")
def _data_embed(
    table_id: str,
    method: Annotated[str, typer.Option(help="pca / tsne")] = "pca",
    columns: Annotated[str | None, typer.Option(help="対象列（カンマ区切り。省略時は数値列から id を除く）")] = None,
    seed: Annotated[int, typer.Option(help="乱数種")] = 0,
) -> None:
    """テーブルを 2D に埋め込み、要約（寄与率・行数・抽出の有無）を YAML で出す（座標は marimo で見る）。"""
    import yaml

    from harness.ds import store, unsupervised

    df = store.load(_root(), table_id)
    cols = _feature_columns(df, columns)
    result = unsupervised.embed_2d(df, columns=cols, method=method, seed=seed)
    out = {"table": table_id, "columns": cols, "embed": result.to_dict()}
    typer.echo(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))


@data_app.command("anomaly")
def _data_anomaly(
    table_id: str,
    method: Annotated[str, typer.Option(help="iforest / lof")] = "iforest",
    columns: Annotated[str | None, typer.Option(help="対象列（カンマ区切り。省略時は数値列から id を除く）")] = None,
    top: Annotated[int, typer.Option(help="上位何行を出すか（浮いている行）")] = 20,
    seed: Annotated[int, typer.Option(help="乱数種")] = 0,
) -> None:
    """多変量の異常スコア（大きいほど異常）の分位要約と、浮いている行の上位 n を YAML で出す。"""
    import yaml

    from harness.ds import store, unsupervised

    df = store.load(_root(), table_id)
    cols = _feature_columns(df, columns)
    report = unsupervised.anomaly_scores(df, columns=cols, method=method, seed=seed)
    rows = unsupervised.anomaly_rows(df, report.scores, n=top)
    out = {"table": table_id, "columns": cols, "anomaly": report.to_dict(), "top_rows": rows.to_dicts()}
    typer.echo(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))


@data_app.command("metrics")
def _data_metrics() -> None:
    """評価指標の一覧（METRICS レジストリから生成）。config の thresholds に書ける指標名。"""
    from harness.ds.eval import METRICS

    render_catalog(METRICS, show_task=True)  # MetricEntry＝向き（大/小）の列が自動で付く
    typer.echo("\nthresholds に書くと passes が向き（大/小）を見て合否判定する。本体は sklearn.metrics 素通し。")


@data_app.command("formats")
def _data_formats() -> None:
    """モデル保存形式の一覧（FORMATS レジストリから生成）。save_model の format に書ける名前。"""
    from harness.ds.models import FORMATS

    for name, fmt in sorted(FORMATS.items()):  # FORMATS は素の dict＝薄い描画（render_catalog は Registry 用）
        typer.echo(f"{name}\t{fmt.file_name}\t{fmt.description}")
    typer.echo(
        "\n保存は model_store.save_model(..., format=<名前>)。未表示＝未導入："
        "skops は `uv sync --extra skops`・onnx は `uv sync --extra onnx` で登録される。"
    )


@data_app.command("predict")
def _data_predict(
    work: Annotated[str, typer.Option(help="モデルの作業単位ID（保存時の work）")],
    name: Annotated[str, typer.Option(help="モデル名（保存時の name）")],
    table: Annotated[str, typer.Option(help="入力の table_id（store 保存済みテーブル）")],
    version: Annotated[str | None, typer.Option(help="モデルの版（省略時は現 champion）")] = None,
    out: Annotated[
        Path | None, typer.Option(help="出力ディレクトリ（既定 artifacts/predictions/<name>/<時刻>）")
    ] = None,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """保存済み champion（または指定版）で入力テーブルにバッチ予測し、parquet＋来歴 manifest を書く。

    予測の種類（prediction_kind）で列が変わる（消費側が意味を取り違えないよう manifest にも残す）：
    二値分類＝`prediction`（陽性=ラベル 1 の確率）・回帰＝`prediction`（値）・多クラス＝`proba_0..k-1`
    （クラス数ぶんの確率列＝陽性 1 列に潰さない・黙って Array 列にしない）。
    sidecar の manifest.yaml にモデル版・指紋・入力テーブルの指紋・行数・prediction_kind を残す（来歴付きの予測ログ）。
    """
    from datetime import UTC, datetime

    import numpy as np
    import polars as pl

    from harness import storage
    from harness.ds import cv, store
    from harness.ds import models as model_store

    if version is None:
        champ = model_store.champion(root, work=work, name=name)
        if champ is None:
            raise ValueError(f"{work}/{name}: champion が無い（先に昇格するか --version で版を明示する）")
        version = champ.version
    model, record = model_store.load_model(root, name=name, work=work, version=version)

    df = store.load(root, table)
    if hasattr(model, "predict_proba"):
        proba = np.asarray(cv._predict(model, df, "proba"))
        if proba.ndim == 1:  # 二値＝陽性（ラベル 1）確率の 1 列
            pred_cols = {"prediction": proba}
            prediction_kind = "proba"
        else:  # 多クラス＝クラス数ぶんの確率列（陽性 1 列に潰すと黙って誤るので全列を出す）
            pred_cols = {f"proba_{i}": proba[:, i] for i in range(proba.shape[1])}
            prediction_kind = "multiclass_proba"
    else:  # 回帰＝predict の値
        pred_cols = {"prediction": np.asarray(cv._predict(model, df, "value"))}
        prediction_kind = "value"
    clash = sorted(set(pred_cols) & set(df.columns))
    if clash:  # 入力の既存列を黙って上書きしない（消えると気づけない）
        raise ValueError(f"予測列 {clash} が入力テーブルの既存列と衝突する（入力を消さないため中止）")
    result = df.with_columns([pl.Series(col, values) for col, values in pred_cols.items()])

    created = datetime.now(UTC)
    if out is None:
        out = root / "artifacts" / "predictions" / name / created.strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=True)
    prediction_fingerprint = storage.atomic_write(out / "predictions.parquet", result.write_parquet)
    manifest = {
        "model": {"work": work, "name": name, "version": record.version, "fingerprint": record.fingerprint},
        "input_table": table,
        "data_fingerprint": store.fingerprint_of(root, table),
        "n_rows": df.height,
        "prediction_kind": prediction_kind,
        "prediction_fingerprint": prediction_fingerprint,
        "created": created.isoformat(),
    }
    # manifest は実体の後に書く（存在＝保存完了の印。store/models と同じ作法）。
    storage.write_manifest(out / "manifest.yaml", manifest)
    typer.echo(f"{df.height} 行を予測: {out}")


@data_app.command("saved")
def _data_saved(work: Annotated[str | None, typer.Option(help="作業単位IDで絞る")] = None) -> None:
    """保存済みモデルの一覧（manifest 走査の生成ビュー）。現 champion に ★ を付ける。"""
    from harness.ds import models as model_store

    records = model_store.list_models(_root(), work=work)
    champs = {
        (w, n): champ.version
        for w, n in {(r.work, r.name) for r in records}
        if (champ := model_store.champion(_root(), work=w, name=n)) is not None
    }
    for r in records:
        mark = "★" if champs.get((r.work, r.name)) == r.version else " "
        shown = "  ".join(f"{k}={v:.4f}" for k, v in sorted(r.metrics.items()))
        typer.echo(f"{mark} {r.work}\t{r.name}\t{r.version}\t{shown}")


@data_app.command("experiments")
def _data_experiments(
    results: Annotated[Path, typer.Option(help="実験の results ディレクトリ（metrics_*.yaml の置き場所）")],
    sort_by: Annotated[
        str | None, typer.Option(help="降順に並べる指標名（省略時は最初のファイルの最初の指標）")
    ] = None,
) -> None:
    """実験結果（results/metrics_*.yaml）を集約したリーダーボード（変種×指標）を表で出す。"""
    import polars as pl

    from harness.ds import experiment

    df = experiment.leaderboard(results, sort_by=sort_by)
    if df.height == 0:
        typer.echo(f"実験結果が無い（{results} に metrics_*.yaml が見つからない）")
        return
    with pl.Config(tbl_rows=-1):  # 全変種を出す（既定の 10 行省略だとリーダーボードの中位が「…」で消える）
        typer.echo(str(df))


def _parse_thresholds(pairs: list[str]) -> dict[str, float]:
    """`--threshold 名=値` の繰り返しを dict にする。形式不正は候補つきで止める（agent CLI と同じ作法）。"""
    out: dict[str, float] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise typer.BadParameter(f"--threshold は 名=値 の形式（実際: {pair!r}。例: roc_auc=0.8）")
        try:
            out[name] = float(value)
        except ValueError as exc:
            raise typer.BadParameter(f"--threshold {name} の値が数値でない（実際: {value!r}）") from exc
    return out


@data_app.command("promote")
def _data_promote(
    work: Annotated[str, typer.Option(help="作業単位ID（保存先 work/<work>/models/…）")],
    name: Annotated[str, typer.Option(help="モデル名")],
    version: Annotated[str, typer.Option(help="昇格候補の版（UTC タイムスタンプ）")],
    primary: Annotated[
        str, typer.Option(help="change_threshold で比べる指標（METRICS の kind・向きはレジストリが正本）")
    ],
    threshold: Annotated[
        list[str], typer.Option("--threshold", help="value_threshold の閾値 名=値（繰り返し可。例: roc_auc=0.8）")
    ],
) -> None:
    """評価済みの版を champion へ昇格する（value_threshold＝閾値・change_threshold＝現 champion からの改善）。"""
    from harness.ds import models as model_store

    try:
        promo = model_store.promote_model(
            _root(), work=work, name=name, version=version, thresholds=_parse_thresholds(threshold), primary=primary
        )
    except ValueError as exc:  # 判定で却下（PromotionError）・未登録 primary → 昇格しない＝非ゼロ終了
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    shown = "  ".join(f"{k}={v:.4f}" for k, v in sorted(promo.metrics.items()))
    typer.echo(f"昇格: {promo.work}/{promo.name}/{promo.version}（decided={promo.decided}）")
    typer.echo(f"primary={promo.primary}（higher_is_better={promo.higher_is_better}）  {shown}")
    typer.echo(f"前 champion: {promo.previous_version or 'なし（初回昇格）'}")


@data_app.command("champion")
def _data_champion(
    work: Annotated[str, typer.Option(help="作業単位ID")],
    name: Annotated[str, typer.Option(help="モデル名")],
) -> None:
    """現 champion の版と metrics を表示する（approved の記録の最新が指す版・無ければ「champion なし」）。"""
    from harness.ds import models as model_store

    champ = model_store.champion(_root(), work=work, name=name)
    if champ is None:
        typer.echo(f"{work}/{name}: champion なし（まだ昇格していない）")
        return
    shown = "  ".join(f"{k}={v:.4f}" for k, v in sorted(champ.metrics.items()))
    typer.echo(f"★ {champ.work}\t{champ.name}\t{champ.version}\t{shown}")


@data_app.command("rollback")
def _data_rollback(
    work: Annotated[str, typer.Option(help="作業単位ID")],
    name: Annotated[str, typer.Option(help="モデル名")],
    reason: Annotated[str, typer.Option(help="なぜ戻すか（記録に残す・必須）")],
) -> None:
    """現 champion を前の champion（切り戻し先の 1 段前）へ戻す。判定は通さない（劣る旧良版へ戻せる）。"""
    from harness.ds import models as model_store

    try:
        rolled = model_store.rollback_model(_root(), work=work, name=name, reason=reason)
    except ValueError as exc:  # 戻り先が無い・実体が無い・reason 空 → 戻せない＝非ゼロ終了
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"切り戻し: {rolled.work}/{rolled.name} の champion を {rolled.previous_version} → {rolled.version} へ")
    typer.echo(f"理由: {rolled.reason}")


@data_app.command("promotions")
def _data_promotions(
    work: Annotated[str, typer.Option(help="作業単位ID")],
    name: Annotated[str, typer.Option(help="モデル名")],
) -> None:
    """昇格・却下・切り戻しの記録を古い順に一覧する（監査・履歴）。"""
    from harness.ds import models as model_store

    for rec in model_store.promotions(_root(), work=work, name=name):
        kind = rec.get("kind", "promote")
        status = rec.get("status", "approved")
        typer.echo(f"{rec['decided']}\t{kind}\t{status}\t{rec['version']}\t前={rec.get('previous_version') or '-'}")


def data_main() -> None:
    """`uv run data <サブコマンド>` の入口。"""

    data_app()
