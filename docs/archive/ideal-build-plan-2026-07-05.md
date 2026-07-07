<!-- 2026-07-05 の「理想形ビルド計画」。Fable 4 並列レビュー（DS完成度・DS構造刷新・中核メカニズム・DX/テスト/正本）を統合。
     オーナー判断：Rule of Three の先送りは外し、良い部品・良い構造は今すべて作る。ただし本当に優れた核は温存する。
     resume 用：本ファイル＋docs/ds-review-2026-07-05.md＋docs/structure-review-2026-07.md。正本＝コードと work/EP-13..16。 -->
# 理想形ビルド計画（2026-07-05・EP-12 後）

## 方針
- **Rule of Three の「待ち」を解除**（オーナー判断）。回数に関係なく、良い部品・良い継ぎ目は今作る。DEC を 1 本起こして記録。
- **触らない核**（温存）：run_cv の clone-per-fold と oof_mask／fold_indices の 1:1 検査／TargetAggregate 内側 OOF／
  pm.py の木と lint 群／段階×マーカー検証＋未マーク失敗ガード／STATUS 非コミット／課題を木の外に置く設計／
  e2e が実雛形を叩く方式／plan=outline を咎めない設計。理想＝全書き換えではない。
- 各タスク＝1 PR・テスト先書き・`uv run verify` 緑・**別セッションの独立レビュー**・DEC/ISS 更新まで（DEC-0009）。

## Wave 0 — 衛生（完了・緑）
依存宣言の是正（未使用 ruamel.yaml/jsonschema/pydantic-settings 削除・PyYAML 明示追加）／CI を `--all-extras`＋
`uv lock --check`／Dockerfile `--all-extras`＋`.dockerignore`／`.claude/settings.json` で `.env`・`secrets/` を read 拒否。

## Wave 1 — 中核メカニズムの整合（EP-13）
「core は汎用・ds はプロファイル」の宣言と実装の乖離を閉じる（template-copy が今コア編集を要求＝実害）。
- **core→ds 分離＋プロファイル機構**：`data_app` を `harness/ds/cli.py` へ移動／`harness/profiles.py`（config の `profiles=[...]`）／
  `PM_CHECKS` を組み立て式に（checks.py の `from harness.ds import schema` を除去）／template-copy.md を「config 1 行」に。
- **pm.lint 強化**：REQ 参照の実在検査（error）・未カバー REQ（info）・depends_on 循環検出（error）。
- **config**：URI 解析の一元化（`parse_uri`）・DataConfig の整合 validator・`_root()` 上方探索。

## Wave 2 — 保存とレジストリの継ぎ目刷新（EP-14）
- **storage.py 抽出**（core）：4 作法（URI 解決／原子書き込み／`file_digest` 指紋／manifest 読み書き）の正本 1 か所。
  store/models/schema は薄い方針層に。非 file: URI の扱いを fail-loud で統一（schema の黙示フォールバック廃止）。
- **registry.py 統一**（core）：9 レジストリを `Entry(factory, description, task, tags)`＋`Registry` に。CLI に汎用
  `render_catalog`＋**`data sources` 追加**。description は docstring 由来で test_catalog の精神維持。
- **model format 継ぎ目完成**：`FORMATS` レジストリ＋`save_model(format=)`＋**skops**（optional extra・信頼型リスト）。既定は当面 pickle。
- **schema checks 実評価**：`Column/TableSchema.checks` を `pl.sql_expr` で今評価（依存ゼロ）。pandera は不採用（導出スケッチを DEC に添付）。

## Wave 3 — DS 完成度（EP-15・全部入れる）
順に：**holdout 最終評価の結線**（ISS-0004）→ **多クラス経路**（`task=binary|multiclass|regression`・metric_fn_for に集約・
`_predict` ガード）→ **scale/missing_flags エンコーダ**（今 kNN/線形が NaN で壊れる穴）→ **group-aware CV**
（StratifiedGroupKFold）→ **チューニング継ぎ目**（`tune:`→RandomizedSearch/Halving・nested CV は無料）→
**バッチ推論入口**（`data predict` で champion を消費）→ **datetime/cyclical ブロック** → **dummy ベースライン** →
**calibration**（CalibratedClassifierCV＋brier）→ **feature selection 段**（SELECTORS）→ **experiment leaderboard**
（`data experiments`）→ **説明可能性**（model_importance・PDP・SHAP extra）＋指標追加（r2/mcc/balanced_accuracy/pinball）。
次点：GLM/quantile 回帰・CatBoost extra・OOF blending・leakage_scan・KS/Wasserstein・mutual_information・
bootstrap CI・TransformedTargetRegressor・lag/rolling ブロック・svd エンコーダ・cost-sensitive 閾値。
**入れない**（ノイズ）：RidgeClassifier・RBF-SVC・GaussianNB・imbalanced-learn・PolynomialFeatures・
FeatureHasher・repeated CV・multilabel。

## Wave 4 — 型・機械検査・DX（EP-16）
- **ExperimentSpec**（pydantic・`extra=forbid`）で実験 config を型付け・`threshold`→`decision_threshold`・run_experiment を 4 引数に。
- **doclint**：スキル/AGENTS/method/learnings → DEC・ISS・パス・コマンドの実在検査を PM_CHECKS へ（正本ドリフトを機械で止める・ISS-0003 close）。
- **conventions lint**（ISS-0002）：グローバル種検出・実験 `--test` 必須・skip/xfail の ISS 参照必須（conftest 拡張）。
- **property テスト**（hypothesis 活用）：passes の NaN fail-closed・psi・fixed_split・fold 被覆・エンコーダ不変量。
- **CliRunner スモーク**＋カバレッジ・ラチェット（CI 別ジョブ）／**template-init**（複製の機械化＋複製後 verify）／
  Windows CI ジョブ／status --next／skops 既定化の判断。

## 依存順（要点）
storage→format 継ぎ目／registry→多クラス（Metric entry 形）→ExperimentSpec（task 三値・decision_threshold の語彙）／
core 分離→doclint・conventions（PM_CHECKS の組み立て口に載る）。DS 部品追加は registry 統一の後（レジストリ形が確定してから）。

## 参考リポジトリ（実践MLOps・CTR 予測）からの取り込み
`/Users/kotaro/work/MLOps/reference/mlops-practice-book-main`（pandas/AWS/FastAPI）を調査。大半は本計画の DS 完成度
（Wave 3）と一致＝方針の裏付け。当リポの流儀（polars・ローカル・registry・config・図でなく構造化表）に**翻案して**取り込む：
- **optuna チューニング**（reference は study で log_loss 最小化）→ Wave 3 の tune 継ぎ目（`*SearchCV` を run_cv に渡す＝nested CV 無料／optuna は optional extra）。
- **モデルのメタデータ/カード**（reference metadata.py＝git commit/branch・依存・計算資源）→ manifest に **git commit/branch＋lock 指紋**を追加＋`models.model_card(record)`（DX 監査 §3・DS 監査 P2）。
- **baseline 比較**（reference comparison.py＝logloss・calibration が baseline 以上）→ 当リポの dummy ベースライン＋promote の相対関門で表現。`calibration`（mean(pred)/mean(true)）は診断指標として eval に足す。
- **roc/calibration 曲線**（reference は matplotlib）→ 当リポは**構造化表** `roc_table`（sklearn roc_curve）を追加（calibration_table は既存）。人は marimo で見る。
- **バッチ推論**（reference は FastAPI 実時間＋予測ログ＋モデルレジストリ）→ 当リポは `data predict`（champion を読み table に予測・版と指紋を manifest に・予測をログ）。実時間サービングは将来のプロファイル。
- **不採用**：pandas 前提の base_model 抽象（当リポは sklearn Pipeline＋store の方が素直）／FeatureHasher（target/count で足りる・DS 監査どおり）／pandera（DEC-0011 どおり YAML 正本＋sql_expr で自前・当リポは polars/NaN/複合鍵の扱いを既に持つ）。

## 記録
本計画の着手で DEC-0010（Rule of Three をオーナー判断で前倒し）と、Wave 2 完了時に DEC-0011（保存 4 作法の正本＝storage.py・
検証は pandera 不採用で手書き＋sql_expr）を残す。ISS-0006〜0011 は「待ち」から本計画のタスクへ移す。
