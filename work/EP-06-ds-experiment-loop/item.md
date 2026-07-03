---
id: EP-06
kind: epic
status: in-progress
title: データサイエンスの実験ループ（ローカル完結・テスト先行）
plan: detailed
requirements: [REQ-004]
created: 2026-07-03
---
# EP-06 実験ループ（ローカル完結・テスト先行）

## 目的
基盤（EP-04）の上に実験の一巡を載せる。ネットワーク・サーバ無しで、特徴量→学習→評価→記録→登録を回す。
参考リポ（`draft/reference/ml-competition-template-main`）の考え方を私たちの流儀に合わせて取り込む。

## 進め方（テスト先行＋先コミット。各タスクは「スタブ＋赤テスト→実装→verify緑」を1タスク内で）
着手順（近い順に detailed、遠いものは着手時に分解）：
1. **T-0010 テストの土台**：`tests/conftest.py` に一時プロジェクトのフィクスチャ工場、pytest マーカー（unit/integration/e2e/slow）を pyproject に登録、**穴埋め**＝(a) pm.lint に「done の実験は結果記録が必須」を追加（調査の結論検査と同型）、(b) verified_by の `::名` がファイルに在ることの確認、規約を AGENTS に明記（テスト数値は構成由来のみ・実験は `--test` 必須・skip は課題参照必須・乱数は明示引数）。
2. **T-0011 transforms.py**：Log1p/Identity/StandardScale＋`TargetTransform` Protocol（numpy のみ・純粋）。参考リポ `domain/transforms.py` の移植。出典ヘッダ（リポ名・MIT）を付ける。往復（transform→inverse）の性質テスト。
3. **T-0012 eval に閾値選択**：`select_threshold_*`（valid/OOF で選ぶ・train/test で選ばない）。参考リポ `domain/threshold.py`。既知ケースでテスト。
4. **T-0013 features.py**：`FeatureBlock`(Protocol, `fit_transform` 第一級)＋`FeaturePipeline`（登録・行数検証・`describe`）。漏れ検査（分布をずらしたデータで valid 統計の混入を検知）。
5. **T-0014 cv.py**：`make_folds(df,*,n_folds,seed,stratify_by)→(id,fold)表`／`fold_indices(df,folds)→[(train_idx,valid_idx)]`／`run_cv(X,y,splits,trainer,*,seed,metrics)→CVResult(oof,fold_metrics,models)`。fold 割当は split 層に保存。Fake Trainer で結線テスト（OOF が全行埋まる・呼び出し回数）。
6. **T-0015 train.py**：`Trainer`(Protocol, `train(...,*,seed)→FoldOutcome`)＋`SklearnTrainer(model_factory=lambda seed: ...)`＋`target_transform`。同じ seed・データで同一予測（再現性・結合）。
7. **T-0016 models.py**：`save_model`（pickle＋manifest・データ指紋と結ぶ・上書き拒否）／`load_model`（manifest 無しは拒否）／`list_models`（台帳ビュー・status に載る）。
8. **E-0001 実験**：仮説「交互作用特徴量 x1*x2 を足すと予測が改善するか」。`SPEC.md`／`config.yaml`（baseline と +interaction・`test_mode:` 節）／`code/train.py`（`--test` スモーク＝`store.load→make/load folds→FeaturePipeline.fit_transform→run_cv→eval.passes→store.save(OOF・予測)→save_model`）／`results/`。合成データは線形なので棄却の見込み＝「負の結果も記録で完了」の実地確認。E2E スモークを verify に接続。

## 引き継ぐ4つの核（参考リポより。詳細は本セッションの整理）
- fit_transform を第一級にしたデータ漏れ防止の契約（OOF 型では fit_transform(train)≠transform(train)）。
- 分割はインデックス対のリストとして学習系へ（固定分割＝要素1・CV＝要素k）。fold は split 層のテーブルに保存し再現をデータで担保。
- FoldTrainer 差し替え（Protocol）で sklearn→LightGBM の移行路。seed は train の明示引数。
- SPEC 先行・1仮説1実験・`--test` スモークを verify に接続（雛形乖離・二重実装を機械的に防ぐ）。

## やらないこと（この段階の範囲外）
- S3/DWH/GitHub Issues 実アダプタ・MLflow・LightGBM 本実装（Trainer の差し替え先として後続）・feature blocks 部品ライブラリ（実験駆動で増やす）。
