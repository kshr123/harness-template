---
name: features
description: 特徴量やエンコードを追加・変更する際に自動参照。まず用意済みの一覧（uv run data blocks / data encoders）から選び、無ければ「sklearn が十分か」（DEC-0008）で作るか使うかを決める。特徴量・エンコード・前処理・変換・feature の語で発火。
---

# features（特徴量は「選ぶ → 無ければ基準で決めて作る」）

## 手順
1. `uv run data blocks`（特徴量ブロック）と `uv run data encoders`（sklearn エンコーダ）で一覧を見る。**あるなら config の features / encode 節に 1 項目足すだけ**（コードは書かない。書き方は一覧の説明と E-0001 の config.yaml）。
2. 無いとき、作る/使うの基準は「**sklearn がそれを十分うまくやっているか**」（DEC-0008。データ依存かどうかではない）：
   - sklearn にある → `src/harness/ds/pipeline.py` の ENCODERS に工場を 1 つ足す。焼き込む既定は「落ちない・漏れない・決定的」の 3 点だけ（性能の好みは焼かず params で上書き可能に）。
   - sklearn に無い隙間（list 列・target の mean 以外の統計・多キー結合の類）→ `features.py` に FeatureBlock を作り、BLOCKS に 1 行足す。
3. 作ったら**同じタスクで**：docstring（何を作るか・有状態か・漏れ対策・config での書き方）＋ unit テスト（行数不変・列名・有状態なら fit/transform の分離・漏れ検知）＋ `uv run data blocks`/`data encoders` に載ることの確認（載らない＝登録漏れ＝使えるようにする一式の欠け）。

## 教師なしの量を特徴にする（クラスタ・異常スコア）
目的変数なしで作った量を下流の入力にするなら encode 節（`uv run data encoders`）：`cluster`（クラスタとの距離が既定＝
KMeans.transform／`output: label` で番号 1 列）・`anomaly_score`（IsolationForest の多変量の外れ・大きいほど異常）。
**fit-on-train は run_cv の clone-per-fold が構造で担保**（pca と同じ経路・漏れ対策の分岐は書かない）。探索だけしたい
（学習に戻さない）なら eda スキルの `data cluster/embed/anomaly`。transform できない手法（t-SNE・HDBSCAN）は
encode 節に載らない＝探索専用（構造でそう決めてある）。

## してはいけないこと
- OneHot / Ordinal / TargetEncoder(mean) / KBins / PCA / Tfidf を自作しない（sklearn を使う・DEC-0008）。
- 漏れ対策を自作しない（外側は run_cv の clone-per-fold、OOF は TargetEncoder / TargetAggregate の内蔵が正本）。
- レジストリに登録せず実験コードから直接 import して使う抜け道を作らない（config から引けない部品は次の実験で再発明される）。
