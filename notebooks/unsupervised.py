"""教師なし（次元圧縮・クラスタ・異常検知）の人向けビュー（marimo）。正本ではない——`harness.ds.unsupervised`
の関数を呼んで図と表にするだけ（eda ビューと同じ流儀）。

集計・結論はここに書かない（正本は `uv run data embed/cluster/anomaly` の YAML と調査単位の results/）。
使い方：案件の調査フォルダへこのファイルをコピーし、テーブルを環境変数で指定して開く。
  - 対話探索：`uv run marimo edit <コピー先>`
  - 閲覧：      `uv run marimo run  <コピー先>`
  - 環境変数：HARNESS_UNSUP_TABLE（表ID・既定 synthetic）／HARNESS_UNSUP_COLUMNS（対象列をカンマ区切り・空なら
             数値列から id を除く）／HARNESS_UNSUP_COLOR（散布図の色分け列＝目的変数でもクラスタでも・空なら単色）
末尾の `app.run()` により `python notebooks/unsupervised.py` で全セルがヘッドレス評価される（e2e スモークが
これを叩いて腐りを防ぐ・図の画素は比較しない）。
"""

import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo
    import polars as pl
    import polars.selectors as cs

    from harness.ds import store, unsupervised

    return Path, cs, mo, os, pl, store, unsupervised


@app.cell
def _(Path, os):
    # パラメータは環境変数で受ける（python 直実行でも marimo edit でも同じ口で効く）。
    root = Path.cwd()
    table_id = os.environ.get("HARNESS_UNSUP_TABLE", "synthetic")
    columns_env = os.environ.get("HARNESS_UNSUP_COLUMNS", "")
    color = os.environ.get("HARNESS_UNSUP_COLOR", "")
    return color, columns_env, root, table_id


@app.cell
def _(mo, table_id):
    mo.md(
        f"# 教師なしビュー — `{table_id}`\n"
        f"正本は `uv run data embed/cluster/anomaly {table_id}` の YAML。ここは同じ関数の表示。"
    )
    return


@app.cell
def _(columns_env, cs, root, store, table_id):
    df = store.load(root, table_id)  # store 経由＝検証済みテーブルだけを見る
    # 対象列：環境変数指定があればそれ、無ければ数値列から id を除く（CLI の既定と同じ・id はリークの温床）。
    if columns_env:
        cols = columns_env.split(",")
    else:
        cols = [c for c in df.select(cs.numeric()).columns if c != "id"]
    return cols, df


@app.cell
def _(mo):
    mo.md("## 2D 埋め込み（PCA）\n座標は近いほど似ている。色は下の設定列（HARNESS_UNSUP_COLOR）。")
    return


@app.cell
def _(cols, df, unsupervised):
    embed = unsupervised.embed_2d(df, columns=cols, method="pca", seed=0)
    embed.to_dict()  # 寄与率・行数・抽出の有無（marimo が dict を表示）
    return (embed,)


@app.cell
def _(color, df, embed, pl):
    # 座標に色分け列を貼って散布図（抽出時は sample_rows で元 df の該当行だけ揃える）。
    coords = embed.coords
    if embed.sample_rows is not None:
        color_df = df[embed.sample_rows]
    else:
        color_df = df
    if color and color in color_df.columns:
        coords = coords.with_columns(pl.Series(color, color_df[color].to_list()))
        chart = coords.plot.point(x="dim1", y="dim2", color=color)
    else:
        chart = coords.plot.point(x="dim1", y="dim2")
    chart.properties(title="PCA 2D 埋め込み")
    return


@app.cell
def _(mo):
    mo.md("## クラスタ（KMeans・k=3）\nクラスタの大きさ・シルエット・クラスタ別の数表。")
    return


@app.cell
def _(cols, df, unsupervised):
    cluster = unsupervised.cluster_summary(df, columns=cols, method="kmeans", seed=0, n_clusters=3)
    cluster.sizes  # クラスタの大きさ（marimo が polars を表として描画）
    return (cluster,)


@app.cell
def _(cluster, mo):
    mo.md(f"シルエット（大きいほど分離が良い）：`{cluster.silhouette}`")
    return


@app.cell
def _(cluster):
    cluster.profile_by_cluster  # クラスタの「顔」（数値列の平均・中央値）
    return


@app.cell
def _(cluster, embed, pl):
    # 埋め込み座標をクラスタ番号で色分け（非抽出時のみ・行数が揃うとき）。
    if embed.sample_rows is None and embed.coords.height == cluster.labels.len():
        colored = embed.coords.with_columns(cluster=pl.Series("cluster", cluster.labels.to_list()))
        result = colored.plot.point(x="dim1", y="dim2", color="cluster:N").properties(title="クラスタで色分け")
    else:
        result = None
    result
    return


@app.cell
def _(mo):
    mo.md("## 異常検知（IsolationForest）\n多変量の外れ（各列は普通でも組み合わせが変な行）。大きいほど異常。")
    return


@app.cell
def _(cols, df, unsupervised):
    anomaly = unsupervised.anomaly_scores(df, columns=cols, method="iforest", seed=0)
    anomaly.to_dict()  # 分位要約（q50/q90/q99/max）
    return (anomaly,)


@app.cell
def _(anomaly, df, unsupervised):
    unsupervised.anomaly_rows(df, anomaly.scores, n=20)  # 浮いている行の上位（全列＋anomaly_score）
    return


if __name__ == "__main__":
    app.run()
