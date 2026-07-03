# 教師なし部品（次元圧縮・クラスタリング・異常検知）詳細設計

対象：`harness-template`（表形式・sklearn 背骨・ローカル完結）。実装はしない（本書は設計のみ）。
参考：Hands-On Unsupervised Learning 3〜6 章（テーブルに効く範囲だけ拾う。8〜13 章＝深層・時系列は範囲外）。
従う原則：DEC-0006（再発明しない）・DEC-0007（漏れ防止は構造で）・DEC-0008（作る/使うの基準＝sklearn が十分か）・
DEC-0009（部品は入口まで）・Rule of Three・平ら構成・造語なし。

---

## 1. 全体像

教師なし手法の用途は 2 つに割れる。この 2 つは**載せる場所も漏れ対策も違う**ので、最初に分けて設計する。

- **(A) 探索（EDA）用途**：全データに当てて「データの構造」を掴む。出力は構造化レポート（polars/dict）が正本。
  図（2D 散布図・色分け）は marimo ビューが同じ関数を呼んで描くだけ（既存 eda.py と同じ流儀）。
- **(B) 特徴量用途**：下流の教師ありモデルの入力にする（圧縮成分・クラスタとの距離/番号・異常スコア）。
  **fit-on-train が必須**。既存の 3 段 Pipeline（features→encode→model）の encode 段（`ENCODERS`）に載せ、
  漏れ防止は `run_cv` の clone-per-fold が構造で担保する（既存 "pca" とまったく同じ枠）。

新しく置くもの（すべて sklearn の薄い包み。アルゴリズムは 1 行も書かない）：

```
src/harness/ds/unsupervised.py    ← 新モジュール（本書の中心）
  ├ DIMRED / CLUSTERERS / ANOMALY  … kind → 工場（安全既定＋seed 焼き込み）の 3 レジストリ
  ├ (A) レポート関数               … embed_2d / cluster_summary / k_scan / anomaly_scores / anomaly_rows
  └ 薄い包みの transformer         … ClusterLabel / AnomalyScore（sklearn に無い隙間だけ・§4/§5）
src/harness/ds/pipeline.py         ← ENCODERS に 2 行追加（"cluster"・"anomaly_score"。工場は pipeline.py に置く）
src/harness/cli.py                 ← data unsupervised（カタログ）・data embed / cluster / anomaly（レポート）
notebooks/unsupervised.py          ← marimo の薄いビュー（同じ関数を呼ぶだけ・散布図と色分け）
tests/…                            ← 構成から導出した期待値のテスト（§9）
```

データの流れ（(A) と (B) で交わらない）：

```
(A) store のテーブル → unsupervised.embed_2d / cluster_summary / anomaly_scores
      → YAML（uv run data embed/cluster/anomaly）＝正本
      → marimo notebooks/unsupervised.py が同じ関数で散布図・表示
(B) config の encode 節（kind: pca / cluster / anomaly_score）
      → build_estimator → run_cv（clone-per-fold で fit は fold の train だけ）
```

---

## 2. (A) 探索 / (B) 特徴量 の仕分け表

仕分けの規準は 2 つだけ：
1. **transform（新しい行に適用）できるか**。できない手法（t-SNE・Agglomerative・HDBSCAN）は構造上 (B) に
   載せられない → (A) 専用。ENCODERS に登録しないことで「載せられない」を構造で守る。
2. **下流の特徴として実務で出番があるか**（DEC-0008＋Rule of Three）。

| 手法 | (A) 探索 | (B) 特徴量 | 判断 |
|---|---|---|---|
| PCA | ○（2D 埋め込み・寄与率） | ○（既存 ENCODERS "pca"） | 両方。すでにある |
| t-SNE | ○（非線形の 2D 地図） | ×（fit_transform のみ） | (A) 専用で入れる |
| TruncatedSVD | − | ○（tfidf の後段圧縮＝LSA） | tfidf 工場の param で入れる（§3） |
| KMeans | ○（セグメント発見） | ○（距離/番号を特徴に） | 両方入れる |
| GaussianMixture | ○（軟らかい所属・BIC で k） | △ | (A) だけ入れる。(B) は先送り |
| HDBSCAN (sklearn 1.3+) | ○（k 不要・密度・雑音行） | ×（新規行の predict が無い） | (A) 専用で入れる |
| Agglomerative | △ | ×（predict が無い） | 先送り（§11） |
| DBSCAN | △ | × | 先送り（HDBSCAN が実質上位互換） |
| IsolationForest | ○（多変量の外れ行） | ○（異常スコアを特徴に） | 両方入れる |
| LocalOutlierFactor | ○（局所密度の外れ） | △（novelty=True が要る） | (A) だけ入れる。(B) の既定は iforest |
| EllipticEnvelope | △ | △ | 先送り（正規分布仮定が狭い） |
| UMAP / Isomap / ICA / KernelPCA ほか | − | − | 先送り（§11 に復活条件） |

---

## 3. 次元圧縮

### 入れるもの

| kind | sklearn クラス | 用途 | 焼き込む既定（落ちない・決定的だけ） |
|---|---|---|---|
| `pca` | `PCA` | (A)(B) | 既存のまま（中央値埋め＋標準化前置・seed・n_components 必須） |
| `tsne` | `TSNE` | (A) 専用 | `random_state=seed`・`init="pca"`（決定性と安定の定石）。他は sklearn 既定 |
| （tfidf の param） | `TruncatedSVD` | (B) | `_tfidf` 工場に `svd_components` 引数を足し、指定時だけ `TruncatedSVD(n_components, random_state=seed)` を後置（LSA。疎行列を直接受けられる標準手） |

- (A) の 2D 埋め込みは `DIMRED = {"pca": …, "tsne": …}` レジストリ。工場は既存 ENCODERS と同じ
  `factory(seed, **params)` 形（params は sklearn へ素通し・写経しない）。前置はどちらも中央値埋め＋標準化
  （PCA/t-SNE とも尺度に敏感＝統計的必須。既存 `_pca` と同じ理屈）。
- `embed_2d(df, *, columns=None, method="pca", seed, **params) -> EmbedResult`：
  - `columns=None` は数値列すべて（`cs.numeric()`・既存 eda の流儀）。
  - 返り値（dataclass・`to_dict()` 付き）：`coords`（polars：`dim1, dim2` の n 行）・`method`・`n_rows`・
    `columns`（使った列）・`explained_variance_ratio`（pca のみ・tsne は None）。
  - t-SNE は行数が大きいと遅い → `max_rows`（既定 5000・超えたら seed 決定的に等確率抽出し
    `sampled: true` をレポートに残す）。門番にせず事実を書く。
- (B) の特徴圧縮は**既存 "pca" で足りる**（密な数値列の圧縮は PCA が既定解）。TruncatedSVD を独立 kind に
  しない理由：密データでは標準化＋PCA に対する利点が無く、出番は tfidf の疎出力の後段だけ。だから
  tfidf 工場の param として置く（encode 段は ColumnTransformer 1 段＝tfidf→svd の直列は工場内 Pipeline でしか
  組めない、という構造上の理由もある）。

### 入れないもの（→ §11）

ICA・RandomProjection・IncrementalPCA・KernelPCA・SparsePCA・MDS・LLE・DictionaryLearning・UMAP。

---

## 4. クラスタリング

### レジストリ `CLUSTERERS`

| kind | sklearn クラス | 用途 | 焼き込む既定 |
|---|---|---|---|
| `kmeans` | `KMeans` | (A)(B) | 中央値埋め＋標準化前置・`random_state=seed`・`n_clusters` 必須（既定 8 を黙って使わせない） |
| `gmm` | `GaussianMixture` | (A) | 同前置・`random_state=seed`・`n_components` 必須 |
| `hdbscan` | `HDBSCAN`（sklearn 1.3+） | (A) | 同前置。k 不要・雑音は label −1（レポートに雑音行数を出す） |

### (A) セグメント発見

- `cluster_summary(df, *, columns=None, method="kmeans", seed, **params) -> ClusterReport`（dataclass・to_dict）：
  - `labels`（polars Series・n 行。hdbscan の雑音は −1）
  - `sizes`（cluster, count, ratio）
  - `silhouette`（float。クラスタが 1 つ/全部雑音なら None＝落とさない）
  - `profile_by_cluster`（polars：cluster × 数値列の mean/median。クラスタの「顔」を数表で。カテゴリ列の
    深掘りは既存 `eda.category_target_summary` に labels 列を足して呼べばよく、専用関数は作らない）
- `k_scan(df, *, columns=None, method="kmeans", k_values=range(2,11), seed) -> polars.DataFrame`：
  列 = `k, inertia, silhouette`（gmm のときは `bic` も）。**目安の表であって門番にしない**（最良 k を
  自動選択して返す関数は作らない——選ぶのは実験側の判断。docstring に明記）。
- marimo：`embed_2d` の座標に `cluster_summary` の labels で色を付けた散布図＋sizes/profile の表。
  正本はあくまで YAML の数表（散布図の画素は比較しない）。

### (B) クラスタを特徴に：ENCODERS `"cluster"`

- 工場（pipeline.py）：`_cluster(seed, *, n_clusters, output="distance", **params)` →
  `Pipeline([impute(median), scale, KMeans(n_clusters, random_state=seed)])`。
  - `output="distance"`（既定）：KMeans は sklearn の transformer で、transform＝各中心への距離
    （n_clusters 列）。**素通しで済み情報量も多い**（最小の列＝所属クラスタなので番号の上位互換）。
  - `output="label"`：`ClusterLabel`（unsupervised.py の薄い包み・約 15 行）を後置。sklearn に
    「predict を transform として出す」部品が無い隙間だけを埋める（DEC-0008 の「作る」側）。
    出力は整数 1 列。カテゴリとして扱いたければ config で後段に載せず、木モデルにそのまま渡すのが既定
    （OneHot したい場面が 2 回出たら考える）。
- KMeans 以外を (B) に足すのは先送り（gmm の predict_proba 特徴は出番が出たら `ClusterLabel` と同型の包みで）。

---

## 5. 異常検知

### レジストリ `ANOMALY`

| kind | sklearn クラス | 用途 | 焼き込む既定 |
|---|---|---|---|
| `iforest` | `IsolationForest` | (A)(B) | 中央値埋め前置（標準化不要＝木）・`random_state=seed` |
| `lof` | `LocalOutlierFactor` | (A) | 中央値埋め＋標準化前置。(A) は novelty=False のまま fit_predict |

- スコアの向きは **「大きいほど異常」に正規化**して返す（sklearn の `score_samples` は「大きいほど正常」
  なので符号反転だけする。閾値・等級化はしない＝事実の報告だけ）。
- `anomaly_scores(df, *, columns=None, method="iforest", seed, **params) -> AnomalyReport`：
  `scores`（n 行）・`method`・`columns`・分位要約（q50/q90/q99/max）。
- `anomaly_rows(df, scores, *, n=20)`：df の全列＋ `anomaly_score` 列をスコア降順で上位 n。
  **既存 `analysis.worst_rows` と同じ形**（df の列＋スコア列＋降順 head）に揃える——「外している行」と
  「浮いている行」を同じ読み方で見られる。
- **EDA の flags/IQR との住み分け**（docstring に書く）：`eda.profile` の `n_outliers` は **1 列ずつ**の
  Tukey 柵（この列の中で極端な値）。こちらは**多変量**（各列は普通でも組み合わせが変な行を拾う）。
  役割が違うので統合しない。

### (B) 異常スコアを特徴に：ENCODERS `"anomaly_score"`

- 工場（pipeline.py）：`_anomaly_score(seed, **params)` →
  `Pipeline([impute(median), AnomalyScore(IsolationForest(random_state=seed, **params))])`。
- `AnomalyScore`（unsupervised.py・約 15 行）：`score_samples` を持つ推定器を包み、transform で
  「−score_samples」1 列を出す sklearn 互換 transformer。sklearn に無い隙間だけ（DEC-0008 の「作る」側）。
- 「異常行を学習から除くフィルタ」は**作らない**。行を消す変換は FeaturePipeline の行数不変検査と衝突するし、
  除外は実験の判断（config でなくデータ準備の段で行う）。必要が 2 回出たら data 節の前処理として設計し直す。

---

## 6. レジストリ・モジュール・入口（DEC-0009）

### 結論

- **新モジュール `src/harness/ds/unsupervised.py` を 1 つ立てる**（平ら構成のまま）。責務は
  「目的変数なしの構造把握」で独立しており、eda.py（既に約 520 行・記述統計）にも features.py
  （特徴量ブロック）にも寄生させない。中身＝3 レジストリ（DIMRED/CLUSTERERS/ANOMALY）＋(A) レポート関数＋
  薄い包み 2 つ（ClusterLabel/AnomalyScore）。
- **(B) は既存 ENCODERS に 2 行足すだけ**（"cluster"・"anomaly_score"。工場は他のエンコーダと同じく
  pipeline.py に置き、包みクラスだけ unsupervised.py から import）。新レジストリを (B) 用に作らない——
  config の encode 節で選ぶ種はすべて `data encoders` 1 か所で引けるのが DEC-0009 の「引ける」。
- **(A) のレジストリは config には出ない**（関数と CLI の引数 `--method` で選ぶ）。カタログは
  `uv run data unsupervised` 1 コマンドで 3 レジストリをまとめて出す（kind＋docstring 1 行目。
  既存 test_catalog と同じ「説明文必須」検査を掛ける）。

### 入口一覧

| 入口 | 内容 |
|---|---|
| `uv run data unsupervised` | DIMRED/CLUSTERERS/ANOMALY のカタログ（レジストリから生成） |
| `uv run data embed <table_id> [--method pca] [--columns a,b]` | embed_2d の要約 YAML（寄与率・行数・抽出の有無。座標は marimo で見る） |
| `uv run data cluster <table_id> --k 4 [--method kmeans] [--scan 2:10]` | cluster_summary の YAML（sizes・silhouette・profile）。`--scan` で k_scan の表 |
| `uv run data anomaly <table_id> [--method iforest] [--top 20]` | anomaly_scores の要約＋anomaly_rows 上位 n の YAML |
| `uv run data encoders` | "cluster"・"anomaly_score" が自動で載る（既存の仕組み） |
| `notebooks/unsupervised.py` | marimo 薄いビュー。環境変数 `HARNESS_UNSUP_TABLE`／`_COLUMNS`／`_COLOR`（色分け列＝目的変数でもクラスタでも）。散布図＋色分け＋異常上位の強調。末尾 `app.run()` でヘッドレス実行（e2e スモーク） |
| スキル | 既存 `eda` スキルに「構造を掴む（クラスタ・埋め込み・外れ行）→ `data unsupervised` → 各コマンド」の節を追加。既存 `features` スキルに「クラスタ/異常スコアを特徴にするなら encode 節（`data encoders`）」の 1 行。**新スキルは作らない**（散文ガイドの二重化を避ける・DEC-0009 の「導かれる」は既存スキル→カタログの導線で満たす） |

- 行単位の成果物（座標・ラベル・スコア）を store に保存する `--save` は**付けない**。全データで付けた
  ラベル/スコアを保存すると「それを特徴に流用」する漏れ経路になる。特徴にしたければ encode 節を通る
  （fit-on-train が構造で効く）一本道にする。

---

## 7. 漏れと決定性

| 論点 | 決め |
|---|---|
| (A) は全データで良いか | 良い（記述的・目的変数を使わない）。ただし docstring に明記：「このレポートは記述。ここで決めた k・除外行・列選択を学習に持ち込むのは通常の EDA と同じ扱いだが、**fit 済みの物（中心・スコア）を特徴量として持ち込むのは禁止**（encode 節を通す）」 |
| (B) の fit-on-train | 構造で担保：ENCODERS → build_estimator → run_cv の clone-per-fold（既存 pca と同一経路。新規コードに漏れ対策の分岐は書かない） |
| 乱数 | すべての工場が `factory(seed, **params)`（既存 ENCODERS と同型）。KMeans/GMM/t-SNE/IsolationForest に `random_state=seed` を焼き込み。グローバル種は使わない（AGENTS の決まり） |
| t-SNE の transform 不可 | ENCODERS に登録しない＝(B) に構造上載らない。docstring：「新しい行を同じ地図に落とせない。(A) 専用」 |
| HDBSCAN/Agglomerative の predict 不可 | 同上（CLUSTERERS のみ・ENCODERS に出さない） |
| LOF | (A) は novelty=False（全データ fit_predict が正しい使い方）。(B) に使いたい場面が出たら novelty=True の包みを検討（先送り） |
| 決定的な出力 | レポートの dataclass は to_dict のキー順固定（eda.py と同じ）。k_scan/sizes は k・cluster 昇順で並べて出す |

---

## 8. 依存

- **追加依存なし**。sklearn>=1.6（現行の ds extra）で HDBSCAN（1.3+）・TSNE・IsolationForest・LOF・
  GaussianMixture・TruncatedSVD すべて賄える。Windows・make 非依存を壊さない。
- **UMAP（umap-learn）・独立版 hdbscan は入れない**。理由：sklearn 外の依存追加＋numba 等の重い連鎖
  （Windows で構築が壊れやすい）。sklearn の HDBSCAN で密度クラスタは足りる。UMAP を将来入れるときは
  lightgbm と同じ流儀（optional extra＋「入っていれば登録」の条件登録・pipeline.py 末尾コメントの §5 方式）で
  DIMRED に "umap" を足すだけの形にしておく（今回のレジストリ設計がその受け口）。

---

## 9. テスト（構成から導出した期待値だけ・金メッキ禁止）

| 層 | テスト | 構成 → 期待値 |
|---|---|---|
| unit | kmeans が 2 塊を当てる | seed 固定で 2 つの離れた塊（中心距離 ≫ ばらつき）を生成 → `cluster_summary(k=2)` の labels と真のラベルの ARI（`sklearn.metrics.adjusted_rand_score`）= 1.0 |
| unit | k_scan の目安が構成と合う | 3 塊のデータ → k_scan(2..5) で silhouette 最大が k=3 |
| unit | hdbscan が塊と雑音を分ける | 2 塊＋遠い数点 → クラスタ数 2・雑音（−1）に仕込んだ点が入る |
| unit | iforest が仕込んだ外れを挙げる | 塊＋原点から大きく離した 5 行 → `anomaly_rows(top=5)` がその 5 行（id で照合） |
| unit | pca 第 1 成分が分散の大半 | x2 = x1 + 小雑音の相関データ → explained_variance_ratio[0] > 0.9 |
| unit | embed_2d の形 | n 行入力 → coords が (n, 2)・全て有限。tsne は小 n（100 行）でスモーク。max_rows 超で `sampled: true` |
| unit | スコアの向き | 仕込んだ外れ行のスコア > 塊の中央の行のスコア（「大きいほど異常」の検査） |
| integration | encode 節で回る | config `encode: [{kind: cluster, columns: […], n_clusters: 2}]` → build_estimator → run_cv が完走・出力列名が get_feature_names_out で追える。anomaly_score も同型 |
| integration | 決定性 | 同じ seed で 2 回呼んで labels/scores/coords が一致 |
| integration | カタログ | `data unsupervised`・`data encoders` に新 kind が載る・docstring 1 行目必須（既存 test_catalog の拡張） |
| e2e | marimo スモーク | `python notebooks/unsupervised.py` がヘッドレスで落ちない（図の画素は比較しない） |

---

## 10. 着手順（歩く骨組み → 差し替え）

まず端まで 1 本通し、verify 全成功を保ったまま広げる（method.md）。

- **T-a 骨組み**：unsupervised.py 新設（CLUSTERERS=kmeans だけ・cluster_summary）＋ CLI `data cluster` ＋
  「2 塊を当てる」unit テスト。→ テーブル → レポート → YAML が一巡。
- **T-b (B) 経路**：ENCODERS "cluster"（distance/label）・"anomaly_score" ＋ ClusterLabel/AnomalyScore ＋
  integration（run_cv 完走・決定性）＋ `data encoders`/test_catalog 反映。
- **T-c (A) を横に広げる**：ANOMALY（iforest/lof）＋ anomaly_scores/anomaly_rows ＋ `data anomaly`／
  DIMRED（pca/tsne）＋ embed_2d ＋ `data embed`／k_scan・gmm・hdbscan ＋ `--scan`・`data unsupervised` カタログ。
- **T-d 入口の仕上げ**：notebooks/unsupervised.py ＋ e2e スモーク／eda・features スキルへの導線追記／
  tfidf の `svd_components`。DEC 起こし（必要なら 1 本：「transform 不可の手法は (A) 専用＝ENCODERS に
  載せない」を規約化。UMAP 先送り等は本設計書と learnings に記録で足りる）。

各タスクは 1 PR 規模。T-a 完了時点で verify が回る状態を維持する。

---

## 11. あえて作らない・先送り一覧（復活条件つき）

| 対象 | 理由 | 復活条件 |
|---|---|---|
| UMAP | 依存追加（numba 連鎖・Windows で重い）。可視化は PCA＋t-SNE で足りる | 数万行超で t-SNE が実用にならない、または「新規行を同じ地図に落とす」必要が実案件で 2 回出たら optional extra＋条件登録で DIMRED に追加 |
| DBSCAN | eps の調整が本質的に難しく、HDBSCAN が実質上位互換 | 距離の尺度が既知で eps を意図して固定したい案件 |
| Agglomerative／樹形図 | predict 不可・KMeans/HDBSCAN で セグメント発見は足りる。樹形図は scipy 依存の図＝正本にできない | 「階層そのもの」（入れ子のセグメント）が要件になったら CLUSTERERS に 1 行 |
| EllipticEnvelope | 正規分布仮定が狭い。iforest/lof で覆える | 楕円仮定が妥当でマハラノビス距離の解釈が要るとき |
| PCA 再構成誤差の異常検知（参考リポ 4 章） | iforest で用が足りる | 「どの列が異常に効いたか」の列別寄与が要る案件が出たら、inverse_transform 差の小関数（10 行）で追加 |
| ICA・RandomProjection・IncrementalPCA・KernelPCA・SparsePCA・MDS・LLE・DictionaryLearning | 表形式の実務で PCA/tSNE/SVD に対する追加の出番がまれ（DEC-0008：sklearn にはあるが今使わない） | 実案件で必要が出たら DIMRED/ENCODERS に 1 行（工場を足すだけの受け口は今回で整う） |
| クラスタ番号の OneHot 化・GMM の所属確率特徴 | 距離特徴（既定）で覆える | 下流モデルがカテゴリ扱いを要求する場面が 2 回出たら |
| 異常行の自動除外フィルタ | 行を消す変換は行数不変の構造と衝突。除外は実験の判断 | データ準備段の前処理として必要が 2 回出たら data 節側で設計 |
| 深層系（autoencoder/RBM/DBN/GAN）・半教師・時系列クラスタリング | 憲法（表形式・sklearn 背骨・深層なし）の範囲外 | プロジェクト方針の改訂（DEC）が先 |
