---
id: EP-30
kind: epic
status: todo
plan: outline
requirements: [REQ-001]
depends_on: [EP-27]
created: 2026-07-10
---
# EP-30 教師なし・時系列の拡充（レジストリの住人を増やす）

## 何をするか
**訂正（独立レビュー 2026-07-10）：`CLUSTERERS`・`ANOMALY`・`DIMRED`・`TS_MODELS` は 4 つとも既に存在する**
（`ds/unsupervised.py` と `ds/forecast.py`）。「軸として立てる」のではない。そう読むと二重実装になる。

実際にやることは 3 つ。
1. 既存の 4 軸に**住人を増やす**（条件登録＝`importlib.util.find_spec` で optional 依存を扱う）。
2. `(B) 特徴経路` の `ENCODERS` を既存の軸へ**接続する**。`ds/pipeline.py` は KMeans / IsolationForest を
   直接 import しており、どの手法を使うかの軸（`method`）が無い（この直書きは実在する）。
3. 符号と契約の非互換を**契約テストで塞ぐ**（下記）。ここが本エピックで最も価値の高い部分。

`SPLITTERS`（分割器を config から選ぶ）も、時系列の purged / embargo という実需要と同時にここで行う
（T-0182。EP-27 から移管）。

## 調べて確かめた事実（実装前に読むこと。ここが本エピックの価値）

### 符号と契約の非互換
- **sklearn の `score_samples` は「低いほど異常」、PyOD の `decision_function` は「高いほど異常」。**
  同じ IsolationForest でも符号が反転する。`ANOMALY` の全 kind に「高いほど異常」を強制する
  契約テストを置き、包む側で符号を揃える。揃えないと `anomaly_score` の意味が kind ごとに変わる。
- `LOF` は `novelty=True` でないと `score_samples` を持たない（学習データにしか使えない）。
- `kmedoids.predict` は `labels_` と別の体系（medoid の**行番号**を返す）。そのまま繋ぐと壊れる。
- `PaCMAP` は `transform(X, basis=X_train)` の形でしか変換できない。
- sklearn の `TSNE` に `transform` は無い。**openTSNE にはある**。帰納的（学習後に新しい行を変換できる）
  にしたいなら openTSNE を採る。

以上から、`DIMRED` と `ANOMALY` は「帰納的に使えるか」を `Entry` の属性として持たせ、
使えない kind を推論経路に接続できないようにする（実行時に黙って壊れない）。

### Python 3.14 で入るもの（実測）
umap-learn 0.5.12 / openTSNE 1.0.4 / pacmap / phate / pyod 3.6.1 / kmodes / kmedoids /
torch 2.13 / mlforecast / skforecast / utilsforecast / prophet / pmdarima / tsfresh / chronos。

### Python 3.14 で入らないもの（実測）
- **statsforecast**：cp314 の wheel が無く、`scipy<1.16` を固定している（3.14 では scipy 1.15.3 に落ち、
  scipy 1.15 系に cp314 wheel が無いのでビルドが要る）。Python 3.13 なら入り、パネル予測・conformal 区間・
  `cross_validation`・ベースラインがすべて動く（実測）。
- **neuralforecast**：~~ray 依存のため 3.14 不可~~ ← **この理由は既に古い（独立レビューによる訂正）**。
  ray 2.56.0 に cp314 wheel が実在し、uv は 3.14 で neuralforecast 3.1.9＋ray 2.56＋torch 2.13 を解決した。
  import までは未確認。**着手時に再測定すること**（依存の可否は日付つきの事実で、すぐ古くなる）。

「時系列だけ 3.13 で回す」は、**今の構造では実現できない**（独立レビューによる訂正）。`checks.toml` は
段階 → argv の列だけを持ち、環境の軸が無い。venv は単一で、`ci_lint` は `uv sync --all-extras` を要求する。
この仕組みは EP-27 の T-0188（まず調査）にあり、まだ存在しない。

したがって本エピックは 2 段に分ける。
- **3.14 に載る範囲**（教師なしの住人・符号の契約テスト・(B) 経路の接続）は T-0188 に依存せず進められる。
- **statsforecast を要する時系列**だけが T-0188 の結論待ち。T-0188 が「環境を分ける価値は無い」と
  結論したら、3.14 に載る範囲で代替するか、時系列のこの部分をやらない。

## 前提
`cluster` / `anomaly_score` 列の黙った上書き（T-0180）を先に直す。列名の衝突を放置したまま
住人を増やすと、壊れ方だけが増える。
