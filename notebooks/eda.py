"""EDA の人向けビュー（marimo）。正本ではない——`harness.ds.eda` の関数を呼んで表と図にするだけ。

集計・指標のロジックと結論はここに書かない（正本は `uv run data profile/compare` の YAML と調査単位の results/）。
使い方：案件の調査フォルダへこのファイルをコピーし、テーブルを環境変数で指定して開く。
  - 対話探索：`uv run marimo edit <コピー先>`
  - 閲覧：      `uv run marimo run  <コピー先>`
  - 環境変数：HARNESS_EDA_TRAIN（表ID・既定 synthetic）／HARNESS_EDA_TEST（比較用の表ID・空なら1表だけ）／
             HARNESS_EDA_TARGET（目的変数の列名・空なら目的変数の要約を出さない）
末尾の `app.run()` により `python notebooks/eda.py` で全セルがヘッドレス評価される（e2e スモークがこれを叩いて
腐りを防ぐ・図の画素は比較しない）。※ compare/PSI/drift のセルは T-0026 で足す。
"""

import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo

    from harness.ds import eda, store

    return Path, eda, mo, os, store


@app.cell
def _(Path, os):
    # パラメータは環境変数で受ける（python 直実行でも marimo edit でも同じ口で効く）。
    root = Path.cwd()
    train_id = os.environ.get("HARNESS_EDA_TRAIN", "synthetic")
    test_id = os.environ.get("HARNESS_EDA_TEST", "")
    target = os.environ.get("HARNESS_EDA_TARGET", "")
    return root, target, test_id, train_id


@app.cell
def _(mo, train_id):
    mo.md(f"# EDA ビュー — `{train_id}`\n正本は `uv run data profile {train_id}` の YAML。ここは同じ関数の表示。")
    return


@app.cell
def _(eda, root, store, train_id):
    train = store.load(root, train_id)  # store 経由＝検証済みテーブルだけを見る
    prof = eda.profile(train)
    return prof, train


@app.cell
def _(mo, prof):
    mo.md("## 列の概要（型・欠損・一意数）")
    return


@app.cell
def _(prof):
    prof.columns  # marimo が polars DataFrame を表として描画する
    return


@app.cell
def _(mo, prof):
    mo.md("## 数値列の統計量")
    return


@app.cell
def _(prof):
    prof.numeric
    return


@app.cell
def _(prof):
    # 欠損の割合を列ごとに棒グラフで（polars の .plot＝altair・図があってもテストは壊れない設計）。
    prof.columns.plot.bar(x="column", y="null_ratio").properties(title="列ごとの欠損割合")
    return


@app.cell
def _(eda, mo, target, train):
    # 目的変数の要約（HARNESS_EDA_TARGET を指定したときだけ）。分類はクラス比率・回帰は統計量。
    if target:
        summary = eda.target_summary(train, target=target)
        mo.md(f"## 目的変数 `{target}` の要約\n\n```\n{summary}\n```")
    return


@app.cell
def _(eda, mo, root, store, test_id, train):
    # 比較（train/test）は HARNESS_EDA_TEST を指定したときだけ。統計量・カテゴリ差・PSI を同じ関数で。
    if test_id:
        comparison = eda.compare(train, store.load(root, test_id))
        mo.md(f"## train/test 比較（test=`{test_id}`）\nPSI 目安：0.1 未満=安定・0.25 以上=大きな変化。")
    else:
        comparison = None
        mo.md("_test 表は未指定（HARNESS_EDA_TEST が空）。1 表だけの要約です。_")
    return (comparison,)


@app.cell
def _(comparison):
    comparison.numeric if comparison is not None else None  # 数値列の train/test 統計と PSI
    return


@app.cell
def _(comparison):
    comparison.categorical if comparison is not None else None  # カテゴリの共通/固有と被覆率
    return


if __name__ == "__main__":
    app.run()
