---
id: EP-15
kind: epic
status: done
title: DS 完成度（多クラス・holdout・エンコーダ群・group CV・tune・predict・calibration・説明可能性・指標）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-14]
created: 2026-07-06
---
# EP-15 DS 完成度（Wave 3・全部入れる）

## 目的
`docs/ideal-build-plan-2026-07-05.md` の Wave 3。DEC-0010 に基づき「あると良い部品/モデルは回数に関係なく全部作る」。
参考リポ（実践MLOps）取り込み（optuna tune・model_card/git provenance・dummy baseline・roc_table・calibration 診断・
バッチ推論）も当リポの流儀（polars・ローカル・registry・config・構造化表）に翻案して同梱する。各部品は DEC-0009 の
「入口まで作って完了」（registry 登録＋docstring＋カタログ/スキル導線）を満たす。

## 進め方（依存順・各タスクは 1 PR・テスト先書き・独立レビュー・verify 緑で done）
1. **T-0051 多クラス経路**（foundational・最初）：task 語彙を `binary|multiclass|regression` に拡張。metric の tasks・
   `metric_fn_for`・`_predict`（proba 列＝クラス数分）・`evaluate`/`passes` を多クラス対応。ISS-0009。
2. **T-0052 holdout 最終評価の結線**（ISS-0004）：experiment ループの holdout を champion 選抜の後に一度だけ評価し
   `results/` に記録。二重評価・リーク（holdout で選抜しない）を検査で固定。
3. **T-0053 指標追加＋診断表**：eval に r2/mcc/balanced_accuracy/pinball、`calibration`（mean(pred)/mean(true) 診断）、
   `roc_table`（sklearn roc_curve の構造化表）。多クラス指標（macro-f1 等）は T-0051 の語彙に乗せる。
3. **T-0054 エンコーダ群**：scale（StandardScaler 相当・kNN/線形の NaN 穴埋め）・missing_flags・datetime/cyclical・
   SELECTORS（feature selection 段）。BLOCKS/ENCODERS に登録＋カタログ。
4. **T-0055 group-aware CV**：StratifiedGroupKFold を cv に。group 列指定でリーク無しの分割。
5. **T-0056 tune 継ぎ目**：`tune:`→RandomizedSearchCV/HalvingSearchCV（optuna は optional extra）。run_cv に *SearchCV を
   渡す＝nested CV 無料。TUNERS registry。
6. **T-0057 dummy ベースライン＋バッチ推論**：DummyClassifier/Regressor を MODELS に。`data predict`（champion を読み
   table に予測・版と指紋を manifest に・予測をログ）。
7. **T-0058 calibration**：CalibratedClassifierCV ラッパ＋brier。promote の相対関門で baseline 以上を表現。
8. **T-0059 experiment leaderboard**：`data experiments`（results を集約した構造化表・champion 表示）。
9. **T-0060 説明可能性**：model_importance（permutation・sklearn）・PDP 表・SHAP（optional extra）＋model_card/git provenance を manifest に。

## やらないこと（ノイズ・plan に明記）
RidgeClassifier・RBF-SVC・GaussianNB・imbalanced-learn・PolynomialFeatures・FeatureHasher・repeated CV・multilabel。
次点（GLM/quantile・CatBoost・OOF blending・leakage_scan・KS/Wasserstein・bootstrap CI 等）は本エピック外・別途。
