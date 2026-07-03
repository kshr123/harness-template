---
id: EP-10
kind: epic
status: in-progress
title: モデルカタログの拡充（分類・回帰・時系列・目的関数変更）
plan: detailed
requirements: [REQ-004]
created: 2026-07-03
---
# EP-10 モデルカタログの拡充（分類・回帰・時系列）

## 目的
分類・回帰・時系列で業界標準のモデルを、config の `model: {kind, ...params}` だけで差し替えられる部品として揃える。
ハイパーパラメータと目的関数（損失）も config から変えられるようにする。目的はコードでなく、将来のエージェントが
再コーディングせず config とスキルでモデルを選べる土台（DEC-0009）。

## 進め方（テスト先行＋先コミット。各タスクは「赤テスト→実装→独立レビュー（静止差分）→verify緑」）
**詳細設計は Fable（`scratchpad/models-catalog-design.md` を DESIGN.md として取り込む・正本）**。利用者の決定：
- **モデルは全部「使う」**（自作ゼロ・DEC-0008）。`MODELS` を `ModelEntry(factory, task)` にし、回帰モデル×分類 task を config 段階で ValueError。
- **目的関数**は文字列 params 素通しが正本（loss/criterion/objective）。カスタム callable は先送り（将来 OBJECTIVES レジストリ）。
- **LightGBM を入れる**（optional extra `lightgbm`・条件登録・未導入でも壊れない）。
- **時系列は ML方式＋古典の両方**：ML方式＝時間順分割（cv に約30行）／古典（ARIMA/SARIMA/ETS）＝statsmodels の別経路（sklearn 背骨に混ぜない・§10）。

**着手順（歩く骨組み・常に verify 緑）**：
1. **T-0031（T-A）レジストリの形**：ModelEntry・build_model の task 検査（task=None 互換）・`data models` に task 列・test_catalog 更新・train.py 雛形1行。既存 2 kind のまま緑。
2. **T-0032（T-B）sklearn モデル一括**：knn/tree/random_forest/hist_gb（分類）・lasso/elasticnet/random_forest_reg/hist_gb_reg（回帰）＋docstring＋構成由来テスト（非線形で木＞線形・目的関数変更が効く・L1 で係数減）＋SKILL.md。
3. **T-0033（T-C）lightgbm**：optional extra＋条件登録＋未導入ヒント＋mypy override＋e2e。
4. **T-0034（T-D）時間順分割（ML方式）**：make_time_folds・fold_indices(how="expanding")・run_experiment(order_by=)＋構造テスト。
5. **T-0035（T-E）古典時系列**：statsmodels（ARIMA/SARIMA/ETS）の別経路（§10・詳細は Fable 設計）。

## やらないこと（先送り・§9/§10）
XGBoost/CatBoost・SVM/SVR/単純ベイズ・多クラス・カスタム目的関数(callable)・ラグ特徴ブロック・予測区間・複数系列・AutoARIMA・
ハイパラ自動探索。いずれも必要になった案件で足す（Rule of Three）。
