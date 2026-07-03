---
id: DEC-0007
status: accepted
date: 2026-07
---
# DEC-0007 実験ループの背骨を sklearn Pipeline にし、自前の fit/transform Protocol を畳む

## 状況（何を決める必要があったか）
段階1で、特徴量変換（TargetTransform）・特徴量ブロック（FeatureBlock 計画）・学習器（Trainer）を
自前の Protocol で定義しかけていた。しかし sklearn 自身が `Pipeline`・`ColumnTransformer`・
`TransformedTargetRegressor`・`TargetEncoder`・estimator 契約でこれらを規定済みで、自前 Protocol は
その焼き直し（二重の抽象）だった。利用者から「sklearn like なインターフェースは特徴量作成のためで、
2 重でやる意味がない」「個別変換（StandardScaler 等）はここでは要らない」「特徴量作成の枠組み＝
BaseBlock の考え方は作れ」「過剰分割を適切な粒度へ・エージェントファーストに」と指摘された。

## 検討した選択肢
- A：自前 Protocol（TargetTransform/FeatureBlock/Trainer）で fit/transform を独自に定義。→ sklearn の焼き直し・二重。
- B：sklearn の Pipeline を背骨にし、特徴量→モデルを1本にして CV の fold ごとに clone。自前は sklearn の外だけ。

## 決定と理由
B を採る。
- **背骨＝sklearn Pipeline**。特徴量→モデルを1本にし、`run_cv` が fold ごとに `sklearn.base.clone` して
  train 側だけで fit する。**漏れ防止が構造になる**（valid の統計が混ざる経路が無い）。旧設計最大の弱点
  （特徴量を CV の前に作る・有状態ブロックで漏れる）が消える。
- **捨てる**：`TargetTransform`/`Identity`/`Log1p`/`StandardScale`（transforms.py 削除。回帰時は
  `TransformedTargetRegressor(func=np.log1p, inverse_func=…)` の 1 行）。`Trainer`/`FoldOutcome`/
  `SklearnTrainer`（sklearn estimator＋clone で足りる。train.py は作らない）。T-0013/T-0015 廃止。
- **作る特徴量枠組み（BaseBlock の考え方・モデル非依存）**：`features.py` の `FeatureBlock`
  （BaseEstimator+TransformerMixin・polars 入出力・名前付き出力・describe）と `FeaturePipeline`
  （ブロックを束ねる薄い sklearn 互換 transformer）。個別の標準変換のブロックは作らず、複数列から作る
  本物の特徴量ロジック（交互作用・集約）だけをブロックにする。
- **一気通貫**：`experiment.py` に `build_estimator`＋`run_experiment`（load→fold→run_cv→eval→保存→results）。
- **構成**：`ds/` を平らな 8 ファイル（data/schema/store/features/cv/eval/models/experiment）。参考リポの
  blocks/・training/ のような過剰分割はしない（1 ファイル 1 責務・名前で引ける＝エージェントファースト）。

理由：battle-tested な sklearn の合成・漏れ防止・estimator 契約に乗ることで、自前抽象の保守負債を無くし、
LightGBM への差し替えも estimator の交換だけになる。ハーネスの価値は fold 表の永続化・run_cv の接着・
合否規約・store/models の永続化・実験構造に集中する。

## 影響（良い点・悪い点・これからやること）
- 良い点：二重抽象を廃し、漏れ防止が構造化。特徴量枠組みはモデル非依存で残り、人にもエージェントにも追いやすい。
- 良い点：モジュールが 8 ファイルの平構成で見通しが良い。
- 悪い点：committed の T-0011（transforms）・T-0014（cv 初版）を部分的に覆す（進化ラチェットの正当な適用）。
- これからやること：DESIGN の R 節が正本（旧 B-2/B-4/D-2/D-3/D-4 を置換）。transforms.py 削除・cv.py 作り直し・
  features.py/experiment.py 新設・E-0001 を一気通貫で。関連 [[DEC-0006]]（標準を再発明しない）。
