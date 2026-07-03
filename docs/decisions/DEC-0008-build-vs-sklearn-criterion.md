---
id: DEC-0008
status: accepted
date: 2026-07
---
# DEC-0008 特徴量ブロックを「作る/使う」の基準は「sklearn が十分か」（データ依存かではない）

## 状況（何を決める必要があったか）
特徴量エンコード（OneHot/Ordinal/TargetEncoder/KBins/PCA/Tfidf/multi-hot）を FeatureBlock として作るか、
sklearn を直接使うかを決める必要があった。当初、実装者は「**出力列がデータに依存するから**我々の
FeatureBlock でなく sklearn 層」という基準で全部を不採用にした。利用者から強い是正：「データ依存はダメと
誰が言った。それこそ特徴量エンジニアリングだ。sklearn like なインターフェースの意味はパイプラインに載る
こと。車輪の再発明は禁止だが、通常の sklearn では足りないものがあるはず（OneHot・target encoding もそう
だった気がする）。最新のベストプラクティスを調べて必要なら作れ」。

## 検討した選択肢
- A（誤り）：データ依存の変換は作らず sklearn 層に置く。→ 「データ依存」を理由に正当な特徴量まで排除。
- B：作る/使うの基準を「**最新の sklearn がそれを十分うまくやっているか**」にする。やっているなら使う
  （再発明禁止・DEC-0006）。足りない隙間があるなら、データ依存でも polars ネイティブの FeatureBlock として作る。

## 決定と理由
B を採る。最新ベストプラクティスを Web で裏取りした結果（sklearn 1.4+）：
- **使う（作らない）**：`OneHotEncoder`（min_frequency で稀カテゴリ束ね・handle_unknown）／`OrdinalEncoder`／
  `TargetEncoder`（1.3+・内部 cross-fitting=OOF＋自動平滑化。target encoding の一番壊しやすい部分を正しく持つ）／
  `KBinsDiscretizer`／`PCA`／`TfidfVectorizer`。すべて `set_output(transform="polars")` で polars 出力可。
  これらを自作するのは純粋な再発明。ColumnTransformer に直接入れる（3段 Pipeline：features→encode→model）。
- **作る（sklearn に無い隙間・データ依存でも）**：`MultiHot`（polars の list 列のタグ展開。sklearn の
  MultiLabelBinarizer は transformer 非準拠で ColumnTransformer に入らない）／`TargetAggregate`（カテゴリ別の
  target の mean **以外**の統計 std/median 等・OOF 内蔵。mean は型で拒否して sklearn TargetEncoder へ回す）／
  `CombineKeys`（多キーを 1 列に結合して sklearn TargetEncoder/CountEncode に渡す前段）。
- **契約の是正**：FeatureBlock の `feature_names()` は「fit 後に確定していればよい」（設定で決まるものは fit 前でも
  返してよい・データ依存は fit 前 NotFittedError）。`FeaturePipeline.fit_transform` を新設し各ブロックの
  fit_transform を通す（これが無いと OOF 型ブロックの cross-fitting 経路が死ぬ）。

## 影響（良い点・悪い点・これからやること）
- 良い点：正当な特徴量エンジニアリング（データ依存）を排除しなくなり、かつ sklearn が良くやるものは再発明しない。
- 良い点：漏れ対策が2段（外側＝run_cv の clone-per-fold／内側＝TargetAggregate の cross-fitting）で明確。
- 悪い点：features.py が伸びる（10 個/500 行で features/ パッケージ化する発火条件は DESIGN R のまま）。
- これからやること：features.py 冒頭 docstring・DESIGN.md R/B-2 の「個別の標準変換は作らない」文言を本基準へ改訂済み。
  実験（E-0002）で 3 段 Pipeline（sklearn encoder 混在）と TargetAggregate を試す。関連 [[DEC-0006]] [[DEC-0007]]。
