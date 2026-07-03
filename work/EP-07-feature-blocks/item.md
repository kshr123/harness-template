---
id: EP-07
kind: epic
status: done
plan: detailed
title: 特徴量エンジニアリングのブロック拡充
requirements: [REQ-004]
created: 2026-07-03
closed: 2026-07-03
---
# EP-07 特徴量エンジニアリングのブロック拡充

## 目的
参考リポ `features/blocks` を精査し、モデル非依存で sklearn が綺麗に持たない特徴量ロジックを、
我々の sklearn 互換 `FeatureBlock`（polars ネイティブ・describe で追える・fold ごと clone で漏れ安全）
として足す。設計は Fable、実装は本セッション。方針は DEC-0006/0007（sklearn を再発明しない）。

## 進め方
- T-0018：Ratios/Differences（無状態）・GroupAggregate/CountEncode（有状態）＋`BLOCKS` レジストリ。
- 今後（実験駆動で足す）：新ブロックは features.py に追記し `BLOCKS` に 1 行。10 個/500 行を超えたら features/ パッケージ化。sklearn で足りるもの（OneHot/TargetEncoder/KBins/PCA/Tfidf/multi-hot）は作らず ColumnTransformer に直接入れる。
