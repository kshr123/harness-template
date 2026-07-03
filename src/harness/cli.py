"""ハーネスの CLI 入口（typer）。`uv run <コマンド>` で呼ぶ。

make は使わない（Windows 含むクロスプラットフォームのため実体は uv run）。
各コマンドは pyproject.toml の [project.scripts] で公開する。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import typer

from harness import checks, issues, pm

# Windows コンソール（cp932）でも日本語・記号（✓✗✅）を出せるよう UTF-8 に固定。
# クロスプラットフォームの前提（make 非依存と同じ理由）。
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def _root() -> Path:
    return Path.cwd()


def status_main() -> None:
    """作業単位の木から STATUS.md を作り直す（その都度生成・手書き禁止・コミットしない）。

    STATUS.md は生成物なので追跡しない（.gitignore）。「見たいときに作り直す」ため、
    生成物とソース（work/ の木）の一致をコミットのたびに突き合わせる仕掛け（ゲート）は置かない。
    見たいときにこのコマンドを走らせれば、最新の進捗と「人の判断待ち」が得られる。
    """

    root = _root()
    out = root / "STATUS.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pm.render_status(root, extra_pending=issues.open_pending(root)) + "\n", encoding="utf-8")
    typer.echo(f"生成: {out}")


def task_lint_main() -> None:
    """作業単位の検査。ID の重複・depends_on の指す先が無い、を失敗にする（終了コード 1）。"""

    root = _root()
    problems = pm.lint(root)
    errors = 0
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        typer.echo(f"{mark} {p.message}")
        if p.level == "error":
            errors += 1
    if errors:
        typer.echo(f"問題 {errors} 件（失敗）")
        # console_script 入口（typer.run を通さない）なので sys.exit で綺麗に終える。
        # typer.Exit を raise すると未捕捉で Traceback が出る（L-006）。
        sys.exit(1)
    typer.echo("問題なし（未分解・未割り当ては許容）")


def check_main() -> None:
    """共通の検証（fast/standard/full）。合否（成功/失敗）を返す。"""

    def _run(
        level: Annotated[str, typer.Option(help="fast | standard | full")] = "full",
    ) -> None:
        raise typer.Exit(checks.run_check(_root(), level))

    typer.run(_run)


def verify_main() -> None:
    """完了判定＝check full と同じ。すべて成功したら done にできる。"""

    sys.exit(checks.run_check(_root(), "full"))


def changelog_main() -> None:
    """CHANGELOG 生成（Phase 0 ではひな形。Conventional Commits から生成予定）。"""

    typer.echo("changelog: 未実装（Phase 0 骨格）。実装は開発ワークフローの段階で。")


issue_app = typer.Typer(help="課題の登録簿（発見された問題・リスク・疑問）", add_completion=False)


@issue_app.command("list")
def _issue_list(open_only: Annotated[bool, typer.Option("--open", help="未対処(open)だけ")] = False) -> None:
    """課題の一覧。--open で未対処だけ。"""
    for li in issues.load_issues(_root()):
        if open_only and li.issue.state is not issues.IssueState.open:
            continue
        typer.echo(f"{li.issue.id}\t{li.issue.kind.value}\t{li.issue.state.value}\t{li.issue.title or ''}")


@issue_app.command("check")
def _issue_check() -> None:
    """課題の整合検査（作業単位との紐付けが崩れていないか）。verify にも含まれる。"""
    errors = 0
    for p in issues.run_checks(_root()):
        typer.echo(f"{'✗' if p.level == 'error' else '・'} {p.message}")
        errors += 1 if p.level == "error" else 0
    if errors:
        typer.echo(f"問題 {errors} 件（失敗）")
        raise typer.Exit(1)
    typer.echo("課題の整合：問題なし")


@issue_app.command("new")
def _issue_new(
    title: str,
    kind: Annotated[str, typer.Option(help="bug | risk | question")] = "question",
    found_in: Annotated[str | None, typer.Option(help="発見元の作業単位ID")] = None,
) -> None:
    """課題を起票する（open で作る）。github: backend では GitHub 側で行う。"""
    root = _root()
    if kind not in {k.value for k in issues.IssueKind}:
        typer.echo("kind は bug / risk / question のいずれか")
        raise typer.Exit(1)
    directory = issues.local_dir(root)
    if directory is None:
        typer.echo("github: backend では起票は GitHub 側で行う")
        raise typer.Exit(1)
    directory.mkdir(parents=True, exist_ok=True)
    iid = issues.next_id(root)
    meta = f"kind: {kind}\nstate: open\ncreated: {date.today().isoformat()}"
    if found_in:
        meta += f"\nfound_in: {found_in}"
    body = f"# {iid} {title}\n\n## 事象\n\n\n## 根拠・影響\n"
    path = directory / f"{iid}.md"
    path.write_text(f"---\nid: {iid}\n{meta}\ntitle: {title}\n---\n{body}", encoding="utf-8")
    typer.echo(f"起票: {path}")


def issue_main() -> None:
    """`uv run issue <サブコマンド>` の入口。"""

    issue_app()


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
    import inspect

    from harness.ds.features import BLOCKS

    for kind, cls in sorted(BLOCKS.items()):
        # 自前の docstring（親からの継承は使わない）。継承を許すと説明が抜けても親の汎用行が黙って載る。
        doc = cls.__doc__.strip().splitlines()[0] if cls.__doc__ else ""
        params = [p for p in inspect.signature(cls.__init__).parameters if p != "self"]
        typer.echo(f"{kind}\t({', '.join(params)})\t{doc}")
    typer.echo(
        "\n使い方は experiment / features スキル。無いものは DEC-0008（sklearn が十分なら data encoders を見る）。"
    )


@data_app.command("encoders")
def _data_encoders() -> None:
    """sklearn エンコーダの一覧（ENCODERS レジストリから生成）。config の encode 節に書ける kind。"""
    from harness.ds.pipeline import ENCODERS

    for kind, factory in sorted(ENCODERS.items()):
        doc = factory.__doc__.strip().splitlines()[0] if factory.__doc__ else ""
        typer.echo(f"{kind}\t{doc}")
    typer.echo("\nparams は sklearn 本体へ素通し（安全既定だけ焼き込み済み）。対象列は encode 項目の columns で指定。")


@data_app.command("models")
def _data_models() -> None:
    """モデル種の一覧（MODELS レジストリから生成）。config の model 節に書ける kind と task。"""
    from harness.ds.forecast import TS_MODELS
    from harness.ds.pipeline import MODELS

    for kind, entry in sorted(MODELS.items()):
        doc = entry.factory.__doc__.strip().splitlines()[0] if entry.factory.__doc__ else ""
        typer.echo(f"{kind}\t{entry.task}\t{doc}")
    for kind, factory in sorted(TS_MODELS.items()):  # statsmodels 導入時のみ。sklearn 背骨に載らない別経路。
        doc = factory.__doc__.strip().splitlines()[0] if factory.__doc__ else ""
        typer.echo(f"{kind}\ttimeseries\t{doc}")
    typer.echo(
        "\nparams は本体へ素通し（目的関数も loss/criterion/objective で変える・各 docstring 参照）。"
        "\n[timeseries] は run_forecast 用（sklearn Pipeline には載らない）。未表示なら `uv sync --extra statsmodels`。"
        "\n学習済みモデル（保存版）の一覧は `uv run data saved`。"
    )


@data_app.command("profile")
def _data_profile(
    table_id: str,
    target: Annotated[str | None, typer.Option(help="目的変数の列名（付けると分布の要約も出す）")] = None,
    task: Annotated[str, typer.Option(help="classification | regression")] = "classification",
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
        for kind, factory in sorted(registry.items()):
            doc = factory.__doc__.strip().splitlines()[0] if factory.__doc__ else ""
            typer.echo(f"{group}\t{kind}\t{doc}")
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

    for name, metric in sorted(METRICS.items()):
        arrow = "大きいほど良い" if metric.higher_is_better else "小さいほど良い"
        typer.echo(f"{name}\t{metric.task}\t{arrow}\t{metric.description}")
    typer.echo("\nthresholds に書くと passes が向き（大/小）を見て合否判定する。本体は sklearn.metrics 素通し。")


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


def data_main() -> None:
    """`uv run data <サブコマンド>` の入口。"""

    data_app()
