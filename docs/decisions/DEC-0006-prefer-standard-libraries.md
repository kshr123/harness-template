---
id: DEC-0006
status: accepted
date: 2026-07
---
# DEC-0006 業界標準のライブラリを再発明しない（メトリクス・分割・スケーリングは scikit-learn）

## 状況（何を決める必要があったか）
段階1（EP-06）で、評価メトリクス（accuracy・ROC-AUC）・標準化（StandardScaler 相当）・交差検証の分割
（KFold・StratifiedKFold 相当）を自前の numpy で書いていた。当初は「核を sklearn 非 import に保つ」
（DESIGN の D-1 旧版）ことを狙ったが、これは業界標準の再発明であり、保守負債とバグの温床だった。
参考リポ（ml-competition-template）も全メトリクスを `sklearn.metrics` で実装し、分割も sklearn の
KFold/StratifiedKFold を使っている。利用者から「無駄。標準ライブラリを使え」と明確に指摘された。

## 検討した選択肢
- A：自前 numpy を保ち sklearn を核で使わない（旧 D-1）。→ 標準の再発明・バグの温床・テストで正しさを別途担保する負担。
- B：標準の数値・分割・スケーリングは scikit-learn を使い、ハーネス固有の接続（合否・fold 表の保存・実験の編成）だけ自作する。

## 決定と理由
B を採る。`scikit-learn>=1.6` を ds extra の一級依存にし、次を sklearn へ置き換えた：
`eval` のメトリクス（`accuracy_score`/`roc_auc_score`）・`transforms.StandardScale`（`StandardScaler`）・
`cv.make_folds`（`KFold`/`StratifiedKFold`）。閾値選択（T-0012）も `sklearn.metrics` で実装する。
差し替えを保つ境界は残す：**モデルの具体**は Trainer の `model_factory` で注入し train.py は特定モデルを
import しない／**直列化の形式**は Serializer で注入し models.py は形式ライブラリを import しない。
理由：battle-tested な標準実装は自作より正しく・速く・読みやすい。Log1p/Identity は numpy 標準関数
そのものなので追加ライブラリは不要。単一クラスの AUC など標準が例外を投げる縁だけハーネスの方針で吸収する。

## 影響（良い点・悪い点・これからやること）
- 良い点：手書きの数値・分割・スケーリングを廃し、保守負債とバグの温床を除いた。置換後も既存テストが
  そのまま全通過＝手書きは純粋な再発明だった裏付け。
- 良い点：sklearn→LightGBM の移行路（Trainer/Serializer 注入）は保たれ、標準実装の恩恵も受ける。
- 悪い点：ds プロファイルの依存が増える（sklearn＋scipy 等）。土台の中核（PM 層）は従来どおり sklearn 非依存。
- これからやること：DESIGN の D-1 を反転済み・B-1/B-2/B-3 を sklearn 利用に更新済み。AGENTS に
  「標準ライブラリを再発明しない（レビュー観点）」を追記。fixed_split（id ハッシュの安定分割）と
  schema.validate（YAML 由来の軽量検証）は sklearn/pandera に無い/差し替え前提の意図的な自作として残す。
