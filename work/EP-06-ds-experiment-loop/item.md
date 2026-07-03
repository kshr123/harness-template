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
**詳細設計は `DESIGN.md`（正本）**。全体像・各モジュールの型シグネチャ・テストピラミッド・横断的判断（sklearn は ds extra・核は import しない／numpy⇔polars 境界は1点／fold 種は SeedSequence）はそちらを見る。

**着手順は「歩く骨組み（walking skeleton）を先に1本通す」**（DESIGN.md E の結論）。E2E・統合の欠落が主眼なので、結線の不確実性を最初に潰し、以降は常に緑の e2e を保ったまま各部品を差し替える。ID は据え置き・順序だけ変える：
1. **T-0010 テストの土台**（済）：conftest 工場・マーカー・pm.lint 強化・AGENTS 規約。
2. **T-0011 transforms.py**（済）：TargetTransform＋Identity/Log1p/StandardScale。
3. **T-0017 検証の仕組み**（骨組みの前の土台）：checks.toml の段階×テストの目印を対応づけ（fast=unit / standard=integration / full=e2e・いずれも not slow）、既存テストに目印付与、未マーク失敗ガードを conftest に。段階＝検証の深さ、目印＝テストの重さ・範囲。門番(full)は slow を外せる。詳細は DESIGN.md C。
4. **T-0014 cv.py**（骨組みの背骨）：make_folds／fold_indices／holdout_indices／run_cv＋CVResult（oof_mask で未カバー黙認を修正）。tests に FakeTrainer。統合テスト＝結線・fold 表の store 往復。
5. **T-0015 train.py**：Trainer Protocol＋FoldOutcome＋SklearnTrainer（model_factory 注入・src は sklearn 非 import）。ここで sklearn を ds extra に追加。
6. **T-0016（前半）models.py**：save_model／load_model＋manifest・指紋・上書き拒否。
7. **E-0001（骨組み）**：フォルダ・SPEC・config.yaml・code/train.py を作り baseline だけで `--test` を端まで通す。`tests/test_e2e_experiment.py::test_e0001_smoke`（実験スクリプトを subprocess で叩く）を追加＝この瞬間から verify に e2e が載る。
8. **T-0013 features.py**：FeatureBlock／FeaturePipeline／3ブロック（Columns/Interaction/StandardScale）／漏れ検知の統合テスト。train.py をパイプラインに差し替え。
9. **T-0012 eval 閾値選択**：select_threshold_*（OOF/valid で選ぶ）。train.py に接続。
10. **T-0016（後半）**：list_models 台帳・`uv run data models`・load 時の指紋照合。
11. **E-0001（完了）**：interaction 変種・本規模（slow）・results 確定・SPEC の判定で結論を記録して done（棄却でも「負の結果も記録で完了」）。

## 引き継ぐ4つの核（参考リポより。詳細は本セッションの整理）
- fit_transform を第一級にしたデータ漏れ防止の契約（OOF 型では fit_transform(train)≠transform(train)）。
- 分割はインデックス対のリストとして学習系へ（固定分割＝要素1・CV＝要素k）。fold は split 層のテーブルに保存し再現をデータで担保。
- FoldTrainer 差し替え（Protocol）で sklearn→LightGBM の移行路。seed は train の明示引数。
- SPEC 先行・1仮説1実験・`--test` スモークを verify に接続（雛形乖離・二重実装を機械的に防ぐ）。

## やらないこと（この段階の範囲外）
- S3/DWH/GitHub Issues 実アダプタ・MLflow・LightGBM 本実装（Trainer の差し替え先として後続）・feature blocks 部品ライブラリ（実験駆動で増やす）。
