---
id: EP-06
kind: epic
status: done
title: データサイエンスの実験ループ（ローカル完結・テスト先行）
plan: detailed
requirements: [REQ-004]
created: 2026-07-03
closed: 2026-07-03
---
# EP-06 実験ループ（ローカル完結・テスト先行）

## 目的
基盤（EP-04）の上に実験の一巡を載せる。ネットワーク・サーバ無しで、特徴量→学習→評価→記録→登録を回す。
参考リポ（`draft/reference/ml-competition-template-main`）の考え方を私たちの流儀に合わせて取り込む。

## 進め方（テスト先行＋先コミット。各タスクは「スタブ＋赤テスト→実装→verify緑」を1タスク内で）
**詳細設計は `DESIGN.md`（正本）**。全体像・各モジュールの型シグネチャ・テストピラミッド・横断的判断（sklearn は ds extra・核は import しない／numpy⇔polars 境界は1点／fold 種は SeedSequence）はそちらを見る。

**着手順は「歩く骨組みを先に1本通す（全体→詳細）」**（`docs/method.md`）。**2026-07-03 に DEC-0007 でゼロベース再設計**（DESIGN.md R が正本）：背骨は sklearn Pipeline、漏れ防止は fold ごと clone で構造的に担保、自前 Protocol（TargetTransform/FeatureBlock/Trainer）は畳む。ID は再利用しない：
1. **T-0010 テストの土台**（済）。
2. ~~T-0011 transforms.py~~（**差し戻し**：DEC-0007。`TransformedTargetRegressor`＋`StandardScaler` で代替。transforms.py 削除・task ファイル削除）。
3. **T-0017 検証の仕組み**（済）：checks.toml の段階×目印・未マーク失敗ガード。
4. **T-0014 cv.py**（済・**作り直し済み**）：make_folds/fold_indices/holdout_indices／`run_cv(estimator,…)`＝fold ごと clone→train で fit（構造的漏れ防止）／CVResult(oof,oof_mask,fold_metrics,estimators,oof_metrics)。統合テストは sklearn の DummyClassifier/StandardScaler。
5. **T-0013 改・features.py**（次）：`FeatureBlock`(BaseEstimator+TransformerMixin・polars・名前付き出力・describe)＋`FeaturePipeline`（束ねる薄い sklearn 互換）＋例ブロック `Interactions`。個別変換（StandardScaler 等）は作らず sklearn を直接使う。漏れ検知は run_cv 経由（構造）。
6. **experiment.py＋E-0001 骨組み**：`build_estimator(spec, model)`＋`run_experiment(...)`。`code/train.py` は呼ぶだけ。baseline を `--test` で一気通貫・`tests/test_e2e_experiment.py::test_e0001_smoke`（subprocess）で verify に e2e を載せる。
7. **T-0012 eval 閾値選択**：select_threshold_*（sklearn.metrics・OOF/valid で選ぶ）。train.py に接続。
8. **T-0016 models.py**：Pipeline 丸ごと保存・版・指紋・台帳・昇格関門（前半 save/load→後半 registry/promote）。
9. **E-0001 完了**（済）：interaction 変種（自前 `Interactions` ブロック x1*x2）・本規模実行・results 確定・結論記録で done。**棄却**（交互作用は効かず＝負の結果も記録で完了）。**EP-06 は 7/7 で done**。
- ~~T-0015 train.py~~（**廃止**：DEC-0007。sklearn estimator＋clone で代替）。

## 引き継ぐ4つの核（参考リポより。詳細は本セッションの整理）
- fit_transform を第一級にしたデータ漏れ防止の契約（OOF 型では fit_transform(train)≠transform(train)）。
- 分割はインデックス対のリストとして学習系へ（固定分割＝要素1・CV＝要素k）。fold は split 層のテーブルに保存し再現をデータで担保。
- FoldTrainer 差し替え（Protocol）で sklearn→LightGBM の移行路。seed は train の明示引数。
- SPEC 先行・1仮説1実験・`--test` スモークを verify に接続（雛形乖離・二重実装を機械的に防ぐ）。

## やらないこと（この段階の範囲外）
- S3/DWH/GitHub Issues 実アダプタ・MLflow・LightGBM 本実装（Trainer の差し替え先として後続）・feature blocks 部品ライブラリ（実験駆動で増やす）。
