---
name: experiment
description: DS の実験（仮説検証・モデル比較・特徴量の効果確認）を始める際に自動参照。用意済みの部品（build_estimator・run_experiment・store）を config で組み合わせ、学習コードを書かない。実験・仮説・変種・比較・ベースライン・モデル評価の語で発火。
---

# experiment（実験＝1 仮説 1 フォルダ・部品は書かずに組む）

## 手順
1. 仮説を 1 つ決め、`work/…/E-xxxx-<短い説明>/` を作る（item.md は kind: experiment、SPEC.md に仮説と判定基準＝どの指標がいくつ動いたら採択）。
2. 直近の実験フォルダ（無ければ `templates/experiment/`）を丸ごとコピーし、**config.yaml だけを書き換える**。config は `ExperimentSpec`（pydantic v2・extra=forbid・`harness.ds.experiment`）が型の正本で、train.py が起動時に検証する＝**未知キー（typo）・型違い・空の variants は起動時エラー**。`thresholds`（指標名→合否の閾値の辞書）は config キー。**決定境界の float は config キーでなく関数引数** `run_experiment(..., decision_threshold=...)`（既定 0.5）＝雛形は OOF から `select_threshold_max_f1` で選ぶので config に `decision_threshold` は書かない（書くと extra=forbid で起動時エラー）。`metrics`/`stratify_by`/`order_by`/`id_column` は optional な config キーで、雛形が run_experiment へそのまま流す（黙って無視されない）。変種は variants 節（features / encode）で持つ。入力は `data` 節（`{kind: synthetic}` か `{kind: table, table_id: <ID>}`）・目的変数は `target`・モデルは `model` 節（`{kind: logreg, ...params}`）で選ぶ。モデル比較の実験は variant 側に `model` を書く。**回帰の実験**は `task: regression`・`model: {kind: ridge}`・`thresholds: {rmse: ...}` にする（`run_experiment(task=)` が指標と予測の種類を切り替える。分類の閾値選択・保存の後処理は回帰では雛形をコピーして外す）。
3. 特徴量・エンコーダ・モデルは `uv run data blocks` / `data encoders` / `data models`（実データは `data list`）の一覧から kind を選んで config に書く。一覧に無い特徴量は features スキルへ。特徴選択は `uv run data selectors`（config の select 節＝to_numpy と model の間の 1 段・run_cv の clone-per-fold で train のみ選択＝リークなし）、ハイパラ探索は `uv run data tuners`（model 節に tune: を足すと *SearchCV で包む＝nested CV）、`thresholds` に書ける指標名は `uv run data metrics`（向き（大/小）つき・本体は sklearn.metrics）の一覧から選ぶ。入力のデータ源（config の data 節に書ける kind）は `uv run data sources` の一覧から選ぶ。
4. code/train.py は**触らない**：config → `load_dataset` → `build_model` → `build_estimator` → `run_experiment` → store 保存 → results/ を一気通貫で回す雛形（e2e が毎回実行する正本）。入力・モデルも config で選ぶので手を入れる必要はない。
5. `python code/train.py --variant <名> --test` でスモーク → e2e テスト 1 本（subprocess で train.py を叩く）を足し、item の verified_by に明記して verify に接続。
6. 本規模を実行し、SPEC の判定基準どおり結論を results/summary.yaml に記録（負の結果も記録で done）。気づきは `docs/learnings.md` へ。

## モデルの選び方（目安・一覧は `uv run data models`）
- まず**線形でベースライン**（分類 logreg／回帰 ridge・lasso・elasticnet）→ 非線形の余地があれば **random_forest / hist_gb(_reg)**（表形式の第一候補・NaN もそのまま）→ 規模・カテゴリが大きければ **lightgbm**（`uv sync --extra lightgbm`）。knn/tree は素直なベースライン。
- **ハイパラ・目的関数は config の params で変える**（`model: {kind: hist_gb_reg, loss: absolute_error}`＝外れ値に強い／`loss: quantile, quantile: 0.9`＝上振れ分位／`criterion: entropy`）。どの引数で変えられるかは各 kind の docstring（`data models`）。
- モデル比較は variants にモデルを持つ（`variants: {a: {model: {kind: ridge}}, b: {model: {kind: hist_gb_reg}}}`）。回帰は `task: regression`。
- **時間の順序があるデータ**（時系列予測）は `order_by: <日付/時刻列>` で**時間順分割**（過去→未来の拡大窓・最古 fold は学習専用）。shuffle CV は使わない（未来を先に見ると評価が甘くなる）。ラグ特徴は features スキル（最初の時系列実験で追加）。
- **古典時系列**（単変量で季節構造そのものが主題）は `task: timeseries`＋`data models` の [timeseries] 群（arima/sarima/ets）。config に `order_by`/`horizon`/`n_windows`/`thresholds: {rmse: ...}`。評価は `forecast.run_forecast`（バックテスト＝過去で fit→先の horizon を forecast→実測と比較）で sklearn 背骨とは**別経路**（run_cv・build_estimator に載せない）。まず第一選択は ML 方式（上の `order_by` 付き）で試し、季節の説明や単変量が主眼なら古典へ。雛形は最初の時系列実験が E-0001 の作法（--test 必須・save_folds・results/metrics_*.yaml・e2e 接続）を踏襲して最小の train.py を書く（Rule of Three＝先に2本目の雛形を作らない）。

## 結果の深掘り（すべて OOF/valid の予測で・`analysis`／`eval`）
どこで・どんな行で・どの列で外しているかを構造化レポートで掴み、特徴量の仮説（features スキルへ）に変える。
- **どの層で外すか**：`analysis.segment_metrics(セグメント列, y_true, oof, task=)`（セグメント別指標・回帰は residual_mean 付き）。
- **どんな行で外すか**：`analysis.worst_rows(df, y_true, oof, n=)`（誤差の大きい行）。
- **どの列が効くか**：`analysis.cv_permutation_importance(cv, x, y, splits, metric=, seed=)`（fold の valid だけで並べ替え＝OOF 規律）。
- **分類の深掘り**：`eval.confusion`（何をどれだけ間違えたか）→ `eval.class_metrics`（どちらのクラスが弱いか）→
  `eval.calibration_table`（確率は信じられるか）→ `eval.threshold_table`（境界を動かすとどうなるか）。
- **回帰の残差**：`analysis.residual_summary(y_true, y_pred)`（mean が 0 から離れていれば系統的な偏り）。
- 分布差（EDA の drift_auc）の原因列も `cv_permutation_importance(DriftResult.estimators, ...)` で特定できる。

## 実験のあとで使う部品（入口・迷ったらここ）
- **閾値の選び方**：既定は `eval.select_threshold_max_f1`。運用の目標があるなら `eval.select_threshold_at_recall(..., target=)`（見逃し上限を決める）／`select_threshold_at_precision(..., target=)`（誤検知上限を決める）。**どれも OOF/valid で選ぶ**（train・test では選ばない）。
- **変種の比較（リーダーボード）**：`uv run data experiments --results work/…/results`（`metrics_*.yaml` を集約し変種×指標の表を出す・`--sort-by <指標>` で並べ替え）。
- **champion への昇格**：採択したら `models.promote_model(root, work=, name=, version=, thresholds=, primary=, higher_is_better=)`。絶対関門（`passes`）かつ相対関門（現 champion に primary で勝つ）を満たすときだけ champion を更新する（負けても保存は残る）。現状の一覧は `uv run data saved`（champion に ★）。
- **保存モデルを読む**：`models.load_model(root, name=, work=, version=None)`（再評価・推論。指紋・形式・依存版を検査してから読む）。version 未指定は最新。
- **LLM エージェントの変種比較も同じ流れ**：結果は `metrics_<variant>.yaml` に残し `uv run agent experiments --results <dir>` で比較、昇格は `uv run agent promote --work … --name … --version … --primary exact_match --threshold 名=値`（絶対＋相対の関門は ML と同型・`docs/agent.md`）。
- **ツール込みのエージェント実行（tools[]・往復ループ）も同じ `uv run agent run --test`** でスモークできる（使えるツールは `uv run agent tools`・無ネットワーク）。
- **最終評価（holdout）**：選抜・閾値調整は全行 OOF で済ませ、champion 確定後に**触っていない test（holdout）で一度だけ** `experiment.final_eval_on_holdout(estimator, df_fit, y_fit, df_test, y_test, task=, decision_threshold=, thresholds=)` を呼び、結果を results/ に記録する（呼び出し例は雛形 train.py）。test の取り分けは `data.fixed_split`（id ハッシュの安定分割）。holdout は選抜・閾値調整に使わない（df_fit と id が重なると ValueError）。

## してはいけないこと
- CV・漏れ対策・メトリクス・保存・閾値選択を実験コードに再実装しない（run_experiment / run_cv / eval / store が正本）。
- 変種をコードの分岐で持たない（config の variants で持つ）。一度保存した fold 表を切り直さない。
- 閾値を train や test で選ばない（OOF で選ぶ）。`--test` の無い実験スクリプトを作らない。
