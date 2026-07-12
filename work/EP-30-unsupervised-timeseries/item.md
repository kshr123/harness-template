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

### Python 3.14 で入るもの（計画時の調査。**着手時の再測定で一部が崩れた**＝下記）
umap-learn 0.5.12 / openTSNE 1.0.4 / pacmap / phate / pyod 3.6.1 / kmodes / kmedoids /
torch 2.13 / mlforecast / skforecast / utilsforecast / prophet / pmdarima / tsfresh / chronos。

### 着手時の再測定（2026-07-13・`uv sync --all-extras` を要件として）と、その結果の決定
計画の「入る」は解決（resolve）だけの確認で、**実ビルド＋import＋all-extras 共存**は別だった（L-020）。
- **openTSNE 1.0.4：入る**。`openTSNE.sklearn.TSNE` が sklearn 互換・`n_jobs=1`＋`random_state` で決定的・
  新規行を transform できる（帰納的）。→ DIMRED に住人 `opentsne`（inductive=True）を追加。
- **kmedoids 0.5.5：入る**が `predict` は**近傍メドイドの行番号**を返す（labels_ の 0..k-1 と別体系）。
  `metric="euclidean"` で特徴データを直接扱える。→ CLUSTERERS に `kmedoids` を追加、包み
  `_MedoidLabelAdapter` で predict を labels_ 体系へ写す（計画の主張どおり体系差が実在した）。
- **pmdarima 2.1.1：入る**（cp314 で実ビルド＋import 成功）。auto_arima は AIC 探索＝決定的。
  → TS_MODELS に `auto_arima` を追加（ForecastLike に薄い包み `_PmdarimaForecaster`）。
- **umap-learn：3.14 で入らない**（計画の「入る」は誤り）。pynndescent→numba/llvmlite が 3.14 の wheel を
  持たず、llvmlite が <3.10 専用に落ちてビルド不能。→ umap は見送り、帰納的な非線形埋め込みは openTSNE で賄う。
- **pyod：入るが all-extras を壊す**。pyod→numba が numpy<2.5 を強い、他 extra が要する numpy 2.5 と衝突して
  古い numba（3.14 不可）に落ちる＝`uv sync --all-extras`（verify の要件）が失敗する。→ 異常検知の帰納的な
  住人は sklearn LOF の `lof_novelty`（novelty=True・依存追加なし）で入れ、pyod は見送り（実需要が来たら
  3.13 環境か numpy 固定で別途）。
- **kmodes：入るがカテゴリ専用**で、数値中心の本モジュール（数値列選択・中央値埋め＋標準化・数値の
  レジストリ駆動テスト）に載らない。→ 見送り（カテゴリ列の配線という別の消費者が要る）。
これらの決定は「実需要が来た分だけ住人を足す」と「着手時に実測して計画を鵜呑みにしない（L-020）」に従う。

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
