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
`CLUSTERERS`・`ANOMALY`・`DIMRED`・`TS_MODELS` を軸として立て、条件登録（`importlib.util.find_spec`）で
optional 依存を扱う。`(B) 特徴経路` の `ENCODERS` は KMeans / IsolationForest を直書きしており、
どの手法を使うかの軸（`method`）が無い。ここもレジストリ経由にする。

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
- **statsforecast**：cp314 の wheel が無く、`scipy<1.16` を固定している。
  Python 3.13 なら入り、パネル予測・conformal 区間・`cross_validation`・ベースラインがすべて動く（実測）。
- **neuralforecast**：ray 依存のため 3.14 不可。

Python の版はタスクごとに分ける軸なので、これは「作れない理由」にならない
（`checks.toml` の環境の軸＝EP-27 の環境分離に接続する）。時系列だけ 3.13 で回してよい。

## 前提
`cluster` / `anomaly_score` 列の黙った上書き（T-0180）を先に直す。列名の衝突を放置したまま
住人を増やすと、壊れ方だけが増える。
