---
id: T-0229
kind: investigation
status: done
title: ISS-0011（DS の効率と忠実性）を実測で問い直す＝5 項目中 4 つは既に修正済み・残り 1 は許容
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by: []
---
## 結論（2026-07-18・現コードを実測。ISS-0011 は resolved に）

ISS-0011 が挙げた 5 つの欠陥を現コードで 1 つずつ確かめた。**優先候補として挙げられていた 2 つを含む
4 つは既に修正済み**（多くは EP-18 で）。残る 1 つ（fixed_split の per-row sha256）は run-once の
O(n) コストで、sha256 はクロスプラットフォームで安定した分割を得るための意図的な選択＝ベクトル化で
安定性を捨てるべきでない。よって着手せず、ISS-0011 は EP-18 を指して resolved にする。

### 5 項目の実測
- **silhouette に sample_size（優先候補）**：修正済み。`unsupervised._silhouette` が
  `sample_size=min(len, SILHOUETTE_MAX_ROWS), random_state=seed` で近似（cluster_summary・k_scan とも経由）。
- **TargetEncoder の分類層化（優先候補）**：修正済み。`pipeline._target` が分類=StratifiedKFold・
  回帰=KFold（task は build_estimator が model から注入）。
- **threshold_table の O(n²)＋手書き P/R/F1**：修正済み。`eval._curve` が sklearn の
  `precision_recall_curve` に委譲（手書きを撤去）。
- **eda の Python 行ループ**：修正済み。`missing_patterns`・`duplicate_columns` は polars 式／
  ハッシュ指紋でベクトル化。
- **fixed_split の per-row sha256（着手しない）**：`data.fixed_split` は id ごとに sha256 して bucket に
  割る Python ループ。O(n)・分割は 1 データにつき 1 回。sha256 は版・OS 差に依らない安定なバケット化の
  ための意図的な選択で、polars の非暗号ハッシュに替えると既存分割の再現性が崩れる。速度より安定性を
  採る設計なので、これは欠陥でなく tradeoff。実データで本当に律速になった時に、その事故を動機に見直す。

### 残す判断
「規模で効く欠陥」は観測された時点で個別に直す（L-025 と同じ＝動機の無い最適化 churn を避ける）。
優先候補 2 つが既に済んでいるので、ISS-0011 全体を open のまま置く理由はない。
