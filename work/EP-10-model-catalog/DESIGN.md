# 詳細設計：モデルカタログの拡充（分類・回帰・時系列）

対象リポジトリ：`C:\Users\hj7745\Desktop\mlops\harness-template`
根拠にした正本：`src/harness/ds/pipeline.py`（MODELS/build_model/build_estimator）・`cv.py`（make_folds/fold_indices/run_cv）・
`eval.py`（METRICS/metric_fn_for）・`experiment.py`（run_experiment）・`tests/test_catalog.py`・`src/harness/cli.py`（`data models`）・
`work/EP-06-ds-experiment-loop/DESIGN.md`・DEC-0006/0007/0008/0009・`.claude/skills/experiment/SKILL.md`。
本書は設計のみ（実装しない）。

---

## 0. 全体像（何をどこまでやるか）

**目的**：分類・回帰・時系列で業界標準のモデルを、config の `model: {kind: ..., ...params}` だけで
差し替えられる部品として揃える。ハイパーパラメータと目的関数（損失）も config から変えられるようにする。

**方針の要約**（詳細は各節）：

1. **モデルは全部「使う」**（DEC-0008）。sklearn / LightGBM のクラスをそのまま工場で包む。自作するモデルはゼロ。
   工場が焼き込むのは「seed 配線・落ちない/うるさくない既定」だけで、性能の好みは焼かない（ENCODERS と同じ流儀）。
2. **レジストリの形を METRICS と同型にする**：`MODELS: dict[str, ModelEntry]`（factory ＋ task）。
   これで「回帰モデルを分類 task に使う」を config 検証の段階で止められる（実行時の predict_proba 不在エラーより早く・分かりやすく）。
3. **目的関数は文字列パラメータの素通しで賄う**（loss / criterion / objective）。config は callable を持てないが、
   業界でよく使う目的関数（MAE・分位・Huber・Poisson・Tweedie・gini/entropy）は全部文字列で指定できる。
   カスタム callable は段階1では許さない（レジストリ化の将来形だけ決めて先送り。Rule of Three）。
4. **時系列の第一選択は「新しいモデル」ではなく「新しい分割」**。ML 方式（ラグ特徴＋回帰モデル＋時間順分割）を採り、
   背骨への拡張は「時間順の fold 表＋拡大窓の添字対」の約 30 行だけ。MODELS に task="timeseries" は作らない。
   古典時系列（ARIMA/SARIMA/ETS）は sklearn 背骨と契約が別物なので**背骨に混ぜず、細い別経路（forecast.py）で
   今つくる**（利用者決定で先送りを解除。詳細設計は §10。Prophet は不採用のまま）。
5. **依存はライブラリ名の optional extra**（`lightgbm = [...]`）＋**条件登録**（入っていれば `data models` に載る・
   入っていなければ載らず、kind 指定時のエラーに導入ヒントを出す）。ds extra は今のまま太らせない。

**変更するファイル**（新モジュールは作らない＝平ら構成の維持。例外は §10 の `forecast.py` 1 ファイルのみ＝
別バックボーンを sklearn 系ファイルに同居させない方が追いやすい・1 ファイル 1 責務）：

| ファイル | 変更 |
|---|---|
| `src/harness/ds/pipeline.py` | ModelEntry 導入・工場を約 9 個追加・build_model に task 検査・lightgbm の条件登録 |
| `src/harness/ds/cv.py` | `make_time_folds`（時間順 fold 表）・`fold_indices(how="expanding")`・`make_backtest_folds`（§10） |
| `src/harness/ds/experiment.py` | `run_experiment(order_by=...)` の配線（時間順分割の入口） |
| `src/harness/ds/forecast.py`（新設） | 古典時系列の別経路：`TS_MODELS`・アダプタ・`build_ts_model`・`run_forecast`（§10） |
| `src/harness/ds/models.py` | `TRACKED_DISTRIBUTIONS` に "statsmodels"（§10-5） |
| `src/harness/cli.py` | `data models` の出力に task 列を追加・TS_MODELS の条件付き追記表示（§10-4） |
| `pyproject.toml` | optional extra `lightgbm`・`statsmodels`・mypy overrides に `lightgbm.*`・`statsmodels.*` |
| `tests/test_catalog.py`・新テスト | ModelEntry 対応・構成から導出する統合テスト（§7・§10-6） |
| `.claude/skills/experiment/SKILL.md` | モデルの選び方の目安・目的関数の変え方・時間順分割の 1 行・古典時系列の入口約 6 行（§10-4） |

---

## 1. 追加モデル一覧（洗い出しと仕分けの結論）

### 1-1. 命名規約

- **kind は 1 つの task に 1 対 1**。同じ実体クラス系（RandomForest 等）の分類版は無印、回帰版は `_reg` 接尾辞。
- 名前自体が task を含むもの（ridge/lasso/elasticnet＝回帰、logreg＝分類）は接尾辞なし（既存の `ridge` とも整合）。
- task の正本は kind 名でなく **ModelEntry.task**（機械検査の根拠。名前は人向けの読みやすさ）。

### 1-2. 追加する kind（＋既存 2 つ）

| task | kind | 実体クラス（全部「使う」） | 依存 | 安全既定（工場で焼く） | 主なハイパラ（params 素通し） | 目的関数/損失の変え方 |
|---|---|---|---|---|---|---|
| 分類 | logreg（既存） | sklearn LogisticRegression | ds | seed・max_iter=1000 | C・penalty・class_weight | log-loss 固定（不均衡は class_weight） |
| 分類 | knn | sklearn KNeighborsClassifier | ds | なし（乱数なし・決定的） | n_neighbors・weights・metric | なし（距離ベース。metric で距離を変える） |
| 分類 | tree | sklearn DecisionTreeClassifier | ds | seed | max_depth・min_samples_leaf・class_weight | criterion="gini"/"entropy"/"log_loss" |
| 分類 | random_forest | sklearn RandomForestClassifier | ds | seed | n_estimators・max_depth・max_features・class_weight | criterion="gini"/"entropy"/"log_loss" |
| 分類 | hist_gb | sklearn HistGradientBoostingClassifier | ds | seed | learning_rate・max_iter・max_depth・l2_regularization・class_weight | log_loss 固定（sklearn の仕様） |
| 分類 | lightgbm | lightgbm LGBMClassifier | extra `lightgbm` | seed・verbosity=-1 | n_estimators・num_leaves・learning_rate・scale_pos_weight | objective="binary" 等の文字列（callable は不可＝§3） |
| 回帰 | ridge（既存） | sklearn Ridge | ds | seed | alpha・solver | 二乗誤差固定（正則化 L2） |
| 回帰 | lasso | sklearn Lasso | ds | seed | alpha・max_iter | 二乗誤差固定（正則化 L1＝特徴量選択を兼ねる） |
| 回帰 | elasticnet | sklearn ElasticNet | ds | seed | alpha・l1_ratio | 二乗誤差固定（L1/L2 混合） |
| 回帰 | random_forest_reg | sklearn RandomForestRegressor | ds | seed | n_estimators・max_depth・max_features | criterion="squared_error"/"absolute_error"/"poisson" |
| 回帰 | hist_gb_reg | sklearn HistGradientBoostingRegressor | ds | seed | learning_rate・max_iter・max_depth・l2_regularization | **loss="squared_error"/"absolute_error"/"gamma"/"poisson"/"quantile"（＋quantile=0.9 等）** |
| 回帰 | lightgbm_reg | lightgbm LGBMRegressor | extra `lightgbm` | seed・verbosity=-1 | n_estimators・num_leaves・learning_rate | objective="regression"/"regression_l1"/"huber"/"quantile"/"poisson"/"tweedie"（＋alpha） |
| 時系列 | （新 kind なし） | 上の回帰モデル＋ラグ特徴＋時間順分割で解く（ML 方式＝第一選択） | ds | — | — | 回帰と同じ |
| 時系列 | arima / sarima / ets | statsmodels ARIMA / SARIMAX / ExponentialSmoothing（**MODELS でなく別レジストリ TS_MODELS**・§10） | extra `statsmodels` | 静かな fit（sarima は disp=False） | order・seasonal_order・trend・seasonal・seasonal_periods | モデル自体が予測器。指標は回帰と共通（rmse/mae/mape） |

追加は 9 kind（分類 5・回帰 5 − 既存 1 …分類 knn/tree/random_forest/hist_gb/lightgbm、回帰 lasso/elasticnet/random_forest_reg/hist_gb_reg/lightgbm_reg）。
`data models` の一覧は既存 2 ＋ 9 ＝ **11 kind**（lightgbm 系は extra 導入時のみ表示）。古典時系列の 3 kind は
別レジストリ（TS_MODELS）なので MODELS の数には入らず、statsmodels 導入時のみ `[timeseries]` 表記で追記表示される
（表示合計 14。§10-4）。

### 1-3. 候補に挙がったが**採らない**もの（判定は DEC-0008：sklearn が十分か＋実務での出番）

| 候補 | 判定 | 理由 |
|---|---|---|
| 線形 SVM（LinearSVC） | 作らない | predict_proba が無く分類の背骨（proba 経路・roc_auc/log_loss）に載らない。線形分類は logreg が同等以上に賄う。CalibratedClassifierCV で包めば載るが、その複雑さに見合う出番がない |
| カーネル SVM（SVC）・SVR | 作らない | 学習が O(n²) で表形式の実務では RF/勾配ブースティングに置き換わって久しい。必要になった案件で 1 行（工場 5 行）足せば済む |
| 単純ベイズ（GaussianNB/MultinomialNB） | 作らない | 主用途のテキスト分類は tfidf＋logreg が同等以上。表形式では出番が薄い。復活条件：テキスト主体の案件で logreg より速度が要るとき |
| 線形回帰（LinearRegression＝OLS） | 作らない | ridge（alpha 小）が実質上位互換（多重共線性で壊れない）。既定モデルを 2 本にする理由がない |
| knn_reg・tree_reg | 作らない | 分類の knn/tree は「近傍・説明可能な木」というベースラインの役があるが、回帰の同種は実務の出番が薄い。要る時に 1 行 |
| XGBoost・CatBoost | 先送り | 勾配ブースティングは hist_gb（依存ゼロ）＋ lightgbm（宣言済みの保留の回収）で 2 系統ある。3 本目は「この 2 つで足りない具体」（コンペ・カテゴリ主体データで CatBoost 指名等）が出た時に、lightgbm と同じ型（extra＋条件登録）で 1 タスク。TRACKED_DISTRIBUTIONS へ名前を足すのも同時 |
| 多クラス分類 | 先送り | 現状の背骨が二値前提（`_predict` の proba[:,1]・eval の labels=[0,1]）。モデルでなく評価・予測経路の拡張であり、本設計の範囲外。最初の多クラス案件で別タスク |

---

## 2. MODELS レジストリの拡充設計

### 2-1. レジストリの形：`dict[str, ModelEntry]`（METRICS と同型）

```python
@dataclass(frozen=True)
class ModelEntry:
    """モデル種 1 つの登録情報。factory は sklearn/LightGBM クラスの薄い包み（再発明しない）。

    task：このモデルが解ける課題。build_model が config の task と突き合わせて検査する。
    説明文は factory の docstring 1 行目（uv run data models に載る・test_catalog が必須検査）。
    """
    factory: ModelFactory
    task: Literal["classification", "regression"]

MODELS: dict[str, ModelEntry] = {
    "logreg": ModelEntry(_logreg, "classification"),
    "ridge": ModelEntry(_ridge, "regression"),
    # ...追加分。lightgbm 系は §5 の条件登録でここに入る。
}
```

- 説明文の置き場は今のまま factory の docstring（test_catalog の検査・CLI の生成を変えない）。
  Metric のような description 文字列を二重に持たない。
- `data models` の出力は `kind\t[classification|regression]\t説明 1 行目` に拡張（task が一覧で見える）。

### 2-2. 各工場の設計（安全既定の原則＝ENCODERS と同じ）

焼き込むのは **決定的（seed）・落ちない・うるさくない** だけ。性能の好み（n_estimators・並列数等）は焼かず
sklearn/LightGBM の既定のまま（params で上書き）。すべて `{**defaults, **params}` で params が勝つ。

```python
def _random_forest(seed: int, **params: Any) -> SklearnLike:
    """ランダムフォレスト（分類）。非線形・交互作用に強い定番。task: classification。

    主なハイパラ：n_estimators・max_depth・max_features・class_weight（不均衡）。
    目的関数：criterion="gini"（既定）/"entropy"/"log_loss"。params はそのまま sklearn へ。
    """
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(**{"random_state": seed, **params})

def _hist_gb_reg(seed: int, **params: Any) -> SklearnLike:
    """勾配ブースティング回帰（sklearn HistGradientBoosting）。表形式の第一候補。task: regression。

    主なハイパラ：learning_rate・max_iter・max_depth・l2_regularization。
    目的関数：loss="squared_error"（既定）/"absolute_error"/"poisson"/"gamma"/
    "quantile"（quantile=0.9 を併記）。params はそのまま sklearn へ。
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(**{"random_state": seed, **params})

def _lightgbm(seed: int, **params: Any) -> SklearnLike:
    """LightGBM 分類。大規模・カテゴリ多めで hist_gb より速く強いことが多い。task: classification。

    主なハイパラ：n_estimators・num_leaves・learning_rate・scale_pos_weight（不均衡）。
    目的関数：objective="binary"（既定）等の文字列。導入は `uv sync --extra lightgbm`。
    """
    from lightgbm import LGBMClassifier  # 遅延 import（未導入でもモジュールは壊れない）
    return LGBMClassifier(**{"random_state": seed, "verbosity": -1, **params})
```

個別の注意（docstring に書く内容の設計）：

- **knn**：乱数を使わないので seed を渡さない（引数は受けて捨てる＝工場の署名は統一）。「距離ベースなので
  スケールの違う数値列は encode 段で標準化してから」の 1 行を docstring に必須で入れる。
- **tree/random_forest**：`class_weight="balanced"` の不均衡対応を docstring で案内。
- **hist_gb / hist_gb_reg**：NaN をそのまま扱える（前処理の穴埋め不要）ことを docstring に明記
  （エンコーダの impute 前置きが不要になる利用上の利点）。
- **lightgbm 系**：`verbosity=-1` を既定に焼く（fold ごとの学習ログが CV で洪水になる＝「うるさくない」既定。
  params で上書き可）。完全な決定性が要るときは `deterministic=True` を params で足せることを docstring に書く（既定では焼かない＝遅くなるため）。
- **lasso/elasticnet**：収束警告が出たら alpha か max_iter を動かす、の 1 行を docstring に。

### 2-3. task の検査（回帰モデル×分類 task を config 段階で止める）

```python
def build_model(spec, *, seed: int, task: Task | None = None) -> SklearnLike:
    """config の model 節から 1 つのモデルを作る。task を渡すとモデル種との整合を検査する。"""
    kind = spec.get("kind")
    if kind not in MODELS:
        hint = _extra_hint(kind)   # §5：optional の kind なら導入コマンドを添える
        raise ValueError(f"未知のモデル '{kind}'（{sorted(MODELS)} のいずれか）{hint}")
    entry = MODELS[kind]
    if task is not None and entry.task != task:
        raise ValueError(f"モデル '{kind}' は {entry.task} 用（この実験は task: {task}）")
    params = {k: v for k, v in spec.items() if k != "kind"}
    return entry.factory(seed, **params)
```

- 呼び出し側の変更は実験雛形 `code/train.py` の 1 行（`build_model(cfg["model"], seed=seed, task=task)`）。
  `task=None` の従来呼び出しはそのまま通る（既存テスト・E-0001 を壊さない）。
- 実行時の二重防御（predict_proba 不在で落ちる）は今のままでよい。検査の正本は ModelEntry.task。
- eval 側は既に `_select(task, names)` で指標×task を検査済み。これでモデル×task も同じ強さになる。

---

## 3. ハイパーパラメータと目的関数を config で変える方法

### 3-1. ハイパラ：現行の素通しをそのまま使う（変更なし）

`model: {kind: ..., ...params}` の params は今も素通しで sklearn クラスに届く。追加モデルも同じ。

```yaml
# 例：モデル比較の実験（variants にモデルを持つ＝experiment スキルの既存の流儀）
task: regression
variants:
  baseline:  {model: {kind: ridge, alpha: 1.0}}
  forest:    {model: {kind: random_forest_reg, n_estimators: 500, max_depth: 8}}
  boosting:  {model: {kind: hist_gb_reg, learning_rate: 0.05, max_iter: 300}}
thresholds: {rmse: 1.0}
```

### 3-2. 目的関数/損失：**文字列パラメータの素通し**が正本

sklearn・LightGBM とも目的関数は文字列引数（loss / criterion / objective）なので、
**params 素通しがそのまま目的関数の変更手段になる**。専用の仕組みは作らない（DEC-0006）。

```yaml
# 例：外れ値に強くしたい → MAE 最適化
model: {kind: hist_gb_reg, loss: absolute_error}
# 例：上振れ 90% 分位を当てたい（在庫・容量計画）
model: {kind: hist_gb_reg, loss: quantile, quantile: 0.9}
# 例：LightGBM で Tweedie（保険金額のようなゼロ過剰×右裾）
model: {kind: lightgbm_reg, objective: tweedie, tweedie_variance_power: 1.3}
# 例：木の分割規準を変える
model: {kind: random_forest, criterion: entropy}
```

どの kind が何の引数で目的関数を変えられるかは **docstring（＝`data models` の入口）に必ず書く**（§6 の書式）。

### 3-3. カスタム目的関数（callable）：段階1では**許さない**（将来形だけ決める）

- config（YAML）は callable を持てない。実験雛形 train.py は「触らない」が規約。よってカスタム目的関数の
  置き場が今の構造には無い——これは**意図した制約**とする。文字列で選べる損失（3-2）が業界ユースの大半を覆う。
- **将来形（作る時の形だけ確定・今は作らない）**：`OBJECTIVES: dict[str, Callable]` レジストリを pipeline.py に置き、
  config は `objective: my_asymmetric_loss` のように**名前で参照**、工場が MODELS と同じ流儀で解決する。
  docstring・`data objectives` 一覧・test_catalog 検査も同型。**発火条件＝文字列損失で書けない目的関数が
  実案件で 2 回必要になった時**（Rule of Three。1 回目はその実験の SPEC に「なぜ標準損失で足りないか」を書いて個別判断）。
- 注意点として設計に残す：分位損失で学習した実験の評価は rmse では歪む。pinball loss（`sklearn.metrics.mean_pinball_loss`）
  を METRICS に足すのは「分位回帰の実験が最初に立った時」の 1 行（先送り一覧 §9）。

---

## 4. 時系列の扱い（結論）

### 4-1. 結論：**ML 方式を採用し、背骨への拡張は「時間順分割」だけ。古典時系列は背骨に混ぜず、細い別経路で今つくる（§10）**

**(a) ML 方式（ラグ特徴＋回帰モデル＋時間順分割）は、小さな拡張で背骨にそのまま載る。**

時系列を「新しい task」にしない。理由：モデル（回帰）も指標（rmse/mae/mape）も予測形（value）も回帰と同一で、
違うのは**分割の作り方（shuffle 禁止・train は過去のみ）だけ**。task="timeseries" を足すと eval・predict の分岐が
無意味に増える。変えるのは cv.py の分割 2 関数＋run_experiment の配線のみ：

```python
# cv.py に追加（分割の計算は sklearn TimeSeriesSplit を使う＝再発明しない・DEC-0006）
def make_time_folds(df, *, n_folds: int, order_by: str, id_column: str = "id") -> pl.DataFrame:
    """時間順の fold 割当表 (id_column, fold)。order_by で安定ソートし時間の連続ブロックに等分。

    fold 番号＝時間ブロック番号（0 が最古）。shuffle しない・seed 不要（決定的）。
    既存の make_folds と同じ表形式なので split 層への保存・再現の担保はそのまま効く。
    """

# fold_indices に how を追加（既定 "cv" は現行どおり＝互換）
def fold_indices(df, folds, *, id_column: str = "id", how: Literal["cv", "expanding"] = "cv") -> ...:
    """how="expanding"：fold k(>=1) を valid、fold < k 全部を train にする（過去→未来の拡大窓）。
    fold 0 は valid にならない（最初の学習材料）＝oof_mask が False のまま——CVResult は
    もともと部分カバーを黙認しない設計（oof_mask）なので、そのまま正しく動く。"""
```

- `run_cv` は無変更（添字対のリストを受けるだけ。shuffle は分割側の性質）。
- `run_experiment` に `order_by: str | None = None` を追加：指定時は `make_time_folds`＋`fold_indices(how="expanding")`
  に切り替え（`stratify_by` と同時指定はエラー）。config からは `order_by: 日付列名` の 1 キー。
- リーク方向の防御が**構造**になる：`how="expanding"` は定義上 train の時刻 < valid の時刻。テストもこの構造検査（§7）。
- ラグ・移動平均の特徴量ブロック（`lag`/`rolling`。polars ネイティブ・group_by 対応。shift は過去→現在なので
  CV 前に全行へ適用しても漏れない）は **features.py（EP-07 の流儀）の管轄**であり本設計の範囲外。
  発火条件＝最初の時系列案件（先送り一覧 §9）。時間順分割だけならラグ無しでも「時間とともに分布が動くデータの
  正直な評価」に今すぐ使えるため、分割だけ先に入れる価値がある。

**(b) 古典時系列（ARIMA/SARIMA/ETS）は sklearn 背骨に混ぜず、細い別経路で今つくる（§10）。**

【2026-07 更新】当初の結論は「作らない・別エピック」だったが、**利用者の決定で先送りを解除**し、
本設計の中で別バックボーン経路として設計する（§10）。更新後の整理：

1. **契約が別物＝混ぜない（この根拠は有効なまま・むしろ §10 の設計原理）**：`fit(y)`（単変量・X なし）＋
  `forecast(h)`（先の期間数を指定）であり、SklearnLike（fit(X,y)/get_params/clone）を満たさない。
  clone-per-fold・build_estimator の背骨に載せるには翻訳層（sktime/skforecast 相当）が丸ごと要る＝薄くない。
  だから**背骨に載せる翻訳層は作らず、run_cv を通らない細い別経路（forecast.py）にする**（DEC-0007 の「混ぜない」を維持）。
2. **Rule of Three の判断は利用者決定で上書き**：「2 つ目の具体を待つ」でなく「道具として先に用意する」を採る。
  ただし作るのは最小（3 kind＋バックテスト 1 関数）で、「時系列基盤」化はしない（§10・§9）。
  時系列の**第一選択は今後も ML 方式**（ラグ＋回帰＋時間順分割）。古典は「単変量・少数系列・季節構造が主題」の
  実験用の第二の道具、という序列は変えない。
3. **依存**：statsmodels は wheel 提供で Windows/make 非依存を壊さない（§10-5）。
  **Prophet は不採用のまま**（cmdstan ビルドが Windows で壊れやすい。この判断は維持）。
4. 旧「起こす時の一言メモ」はそのまま §10 の骨格になった：statsmodels（ARIMA/ETS）・背骨に混ぜない・
  時間順ホールドアウト＋`forecast(h)`＋eval.METRICS の回帰指標・fold 表/store/results の規律は共通。

**先回りで作らないことの明示（更新）**：本設計で時系列のために作るのは、cv.py の分割関数（make_time_folds・
expanding・make_backtest_folds）＋run_experiment の 1 引数＋§10 の forecast.py（約 150 行の細い経路）のみ。
「時系列基盤」（予測区間・カレンダー特徴・複数系列の階層・exog 配線・gap/embargo 付き分割・AutoARIMA）は
作らない（§9 に復活条件つきで列挙）。どれも最初の実案件が要求を確定させるまで形を決められない。

---

## 5. 依存戦略（optional extra ＋ 条件登録）

### 5-1. extra の切り方：**ライブラリ名 = extra 名**（1 対 1）

```toml
[project.optional-dependencies]
ds = [...]                      # 今のまま。sklearn 系 9 kind はこれだけで全部動く
lightgbm = ["lightgbm>=4.5"]    # 導入例: uv sync --extra ds --extra lightgbm
# 将来（採用が決まった時に足す・今は書かない）: xgboost / catboost / ts(statsmodels 等)
```

- `models` のような束ね extra は作らない。束ねると「catboost だけ欲しいのに全部入る」が起き、
  1 対 1 なら名前の説明も不要（自己記述）。lightgbm は Windows 含め公式 wheel 提供で make 非依存を壊さない。
- `TRACKED_DISTRIBUTIONS`（models.py）は既に "lightgbm" を含む＝保存 manifest の依存記録はそのまま効く。
  xgboost 等を将来採用したら同時に名前を足す。
- mypy overrides（pyproject）に `lightgbm.*` を追加（sklearn と同じ ignore_missing_imports）。

### 5-2. 「入れなければ効かない・入れれば増える」＝条件登録＋遅延 import

```python
# pipeline.py 末尾。import コストゼロの存在確認（find_spec）で登録だけ切り替える。
# 工場本体は関数内 import（_ridge と同じ流儀）なので、未導入環境でもモジュールは壊れない。
if importlib.util.find_spec("lightgbm") is not None:
    MODELS["lightgbm"] = ModelEntry(_lightgbm, "classification")
    MODELS["lightgbm_reg"] = ModelEntry(_lightgbm_reg, "regression")

# 未導入で kind: lightgbm と書いた時のエラーに導入ヒントを添える材料（§2-3 の _extra_hint が参照）
OPTIONAL_MODEL_EXTRAS: dict[str, str] = {"lightgbm": "lightgbm", "lightgbm_reg": "lightgbm"}
```

- 効果：`uv run data models` は**入っている環境でだけ** lightgbm 系を表示（一覧＝使える語彙、の原則を守る）。
  未導入で使うとエラーが「未知のモデル 'lightgbm'（…）。lightgbm は `uv sync --extra lightgbm` で使えるようになる」
  と出て、エージェントが自力で復帰できる。
- **開発・verify 環境は全部入り**（`uv sync --all-extras`）を規約にする。これで「optional 依存のテストを skip する」
  事態を作らない（テスト規約の「理由なき skip 禁止」と衝突しない）。案件の実行環境だけ必要な extra に絞る。

---

## 6. 入口（DEC-0009：レジストリ＋docstring＋導線＋テスト）

1. **`data models` の拡張**：出力を `kind\t[task]\t説明 1 行目` にし、末尾の案内文に
   「目的関数（loss/criterion/objective）も params で変更できる。詳細は各 kind の docstring」を足す。
2. **docstring の書式（全工場で統一・test_catalog が 1 行目の存在を検査）**：
   - 1 行目＝用途と立ち位置（一覧に載る）。`task: classification|regression` を文中に含める。
   - 2 行目以降＝主なハイパラ（3〜5 個）・**目的関数の変え方（引数名と選択肢）**・注意（スケーリング・不均衡・NaN 可否）。
3. **experiment スキルへの導線**（SKILL.md に追記・約 10 行）：
   - モデルの選び方の目安：「まず線形（logreg/ridge）でベースライン → 非線形の余地は random_forest / hist_gb →
     規模・カテゴリが大きければ lightgbm（`--extra lightgbm`）」。
   - 目的関数の変え方の 1 例（`loss: quantile` の YAML）と「外れ値に強く＝absolute_error」の一言。
   - 時間の順序があるデータは `order_by: <日付列>` で時間順分割（shuffle CV は使わない）の 1 行。
4. **雛形（train.py）**：変更は `build_model(..., task=task)` の 1 行のみ。config でモデルも目的関数も切り替わるので
   再コーディング不要（エージェントファーストの現状を維持）。

---

## 7. テスト（期待値はすべてデータの構成から導出）

| 層 | テスト | 構成からの導出 |
|---|---|---|
| unit | カタログ検査（既存の拡張） | 全 ModelEntry に docstring 1 行目がある・task が classification/regression のいずれか・`data models` の出力に task 表記と追加 kind が載る |
| unit | task 不整合 | `build_model({kind: ridge}, task="classification")` → ValueError（メッセージに kind と task）。逆向き（logreg×regression）も |
| unit | 未導入ヒント | MODELS から lightgbm を一時除去（monkeypatch）→ build_model のエラー文に `--extra lightgbm` が含まれる |
| unit | 決定性 | random_forest / hist_gb：同 seed 2 回で予測 allclose・異 seed で不一致（seed 配線の証拠） |
| integration | **非線形で木が線形に勝つ** | y = 1 [x1·x2 > 0]（XOR 型・線形分離不能）を n=600 で合成 → logreg の roc_auc ≤ 0.65（構成上ほぼ 0.5）・random_forest / hist_gb ≥ 0.85。差は構成（線形分離不能）から導出され実装値のコピーではない |
| integration | **目的関数の変更が効く** | 右に歪んだ雑音の回帰データで hist_gb_reg を loss=quantile, quantile=0.9 と 0.1 で学習 → 前者の予測平均 > 後者（分位損失の定義から導出）。criterion 版：random_forest criterion="entropy" が gini とパラメタとして別物になる（get_params で確認） |
| integration | 正則化の向き | lasso：alpha を大きくすると係数の非ゼロ数が単調に減る（L1 の定義から導出） |
| integration | **時間順分割の構造** | make_time_folds＋fold_indices(how="expanding")：全 fold で max(train の時刻) < min(valid の時刻)・fold 0 は oof_mask False・valid 重複なし。トレンド 100% のデータ（y=t）で shuffle CV より expanding の rmse が大きい（＝未来を知らない正直な評価。構成から導出） |
| e2e | 雛形での一巡 | 既存の実験雛形 config の kind を hist_gb に差し替えた `--test` スモーク 1 本（subprocess・雛形が新モデルでも一巡する証拠）。lightgbm は all-extras 環境で kind 差し替えのパラメタ化 1 ケース |

---

## 8. 着手順（歩く骨組み：常に verify 緑のまま 5 タスク）

| 順 | タスク（各 1 PR 相当） | 内容 | 完了の証拠 |
|---|---|---|---|
| 1 | T-A レジストリの形 | ModelEntry 導入・build_model の task 検査（task=None 互換）・CLI の task 列・test_catalog 更新・train.py 雛形の 1 行 | 既存 2 kind のまま verify 全緑（形だけ先に通す） |
| 2 | T-B sklearn モデル一括 | 7 工場（knn/tree/random_forest/hist_gb/lasso/elasticnet/random_forest_reg/hist_gb_reg）＋docstring＋§7 の unit/integration テスト＋SKILL.md のモデル選び追記 | `data models` に 9 kind・非線形/目的関数/正則化テスト緑 |
| 3 | T-C lightgbm | extra 追加・条件登録・未導入ヒント・mypy override・all-extras 規約の明文化（AGENTS の DS 節 1 行）・e2e 1 ケース | 全部入り環境で 11 kind・未導入分岐は monkeypatch テスト |
| 4 | T-D 時間順分割（ML 方式） | make_time_folds・fold_indices(how="expanding")・run_experiment(order_by=)・構造テスト・SKILL.md 1 行 | §7 の時間順テスト緑・既存の shuffle 経路は無変更で緑 |
| 5 | T-E 古典時系列（§10） | forecast.py 新設（ForecastLike・アダプタ・TS_MODELS 3 kind・build_ts_model・run_forecast）・cv.make_backtest_folds・extra `statsmodels`＋条件登録＋未導入ヒント・TRACKED_DISTRIBUTIONS・mypy override・§10-6 の unit/integration・SKILL.md の入口約 6 行 | all-extras 環境で `data models` に [timeseries] 3 kind・「素朴予測に勝つ」「バックテスト構造」「決定性」テスト緑・sklearn 側は無変更で緑 |

依存関係：T-B と T-C は独立（並行可）。**T-E は T-A（`data models` の出力書式）と T-D（`fold_indices(how="expanding")`
を流用）の後**。T-B/T-C とは独立（並行可）。T-E をやると決めた時点で T-D の優先度は上がる（T-D → T-E の順が確定）。
最初の時系列実験（＝古典 TS 用 train.py のコピー元づくり。§10-4）は T-E の後、実案件か合成データで 1 本立てる
（T-E のタスク範囲には含めない＝Rule of Three）。

---

## 9. あえて作らない・先送り一覧（復活条件つき）

| 項目 | 判断 | 復活条件 |
|---|---|---|
| 線形/カーネル SVM・SVR・単純ベイズ・OLS・knn_reg/tree_reg | 作らない | 実案件で指名された時に工場 5 行＋docstring＋テスト 1 本（半日仕事） |
| XGBoost・CatBoost | 先送り | hist_gb/lightgbm で足りない具体が出た時。extra＋条件登録の同じ型・TRACKED_DISTRIBUTIONS へ名前追加も同時 |
| カスタム目的関数（callable） | 先送り | 文字列損失で書けない目的関数が 2 案件目で必要になった時に OBJECTIVES レジストリ（§3-3 の形で） |
| pinball loss 指標（分位回帰の評価） | 先送り | 分位損失の実験が最初に立った時に METRICS へ 1 行（mean_pinball_loss） |
| 多クラス分類（proba 多列・指標） | 先送り | 最初の多クラス案件。モデルでなく predict/eval 経路の拡張として別タスク |
| ラグ・移動平均の特徴量ブロック | 先送り | 最初の時系列案件で features.py（EP-07 の流儀）に lag/rolling を追加（polars ネイティブ・group_by 対応） |
| 古典時系列（ARIMA/SARIMA/ETS） | **今つくる（§10・T-E）** | —（利用者決定で先送りを解除。sklearn 背骨には混ぜない別経路＝forecast.py） |
| Prophet・sktime/skforecast 等の翻訳層 | 作らない | Prophet は Windows（cmdstan ビルド）で壊れやすい。翻訳層は fit(y)/forecast(h) の統一契約（§10-2）で足りている間は不要 |
| 予測区間（forecast の信頼区間） | 先送り | statsmodels の get_forecast().conf_int() で取得自体は安いが、results/thresholds への接続形が未確定。区間が判定基準になる最初の案件で ForecastResult に列を足す |
| AutoARIMA（statsforecast） | 先送り | 依存追加（numba 系）で重い。次数選定は当面 variants に order 違いを並べる既存の比較で賄う。系列数が増えて手動選定が回らなくなった時に extra＋条件登録の同じ型で 1 タスク |
| exog（SARIMAX の説明変数）配線 | 先送り | 未来の説明変数を h 期間ぶん用意する経路が config・データ設計を要求する。未来 covariates が確定した最初の案件で run_forecast 側の配線のみ追加（SARIMAX 自体は素通しで受けられる） |
| 複数系列（系列 ID ごとの予測・階層） | 先送り | 系列数 > 1 の最初の案件。素朴には系列ごとのループで足りるかをまず確認（run_forecast は order_by の重複をエラーにして単一系列を守る） |
| naive / seasonal_naive の kind 登録 | 先送り | テストでは素朴予測をテスト内で計算する。実案件で results にベースライン比較を残したくなったら TS_MODELS に約 10 行 |
| 欠測期間の穴埋め・再サンプリング | 先送り | run_forecast は等間隔前提（y を数列として渡す）。欠けた期間のあるデータが来た最初の案件で data 側の前処理として設計 |
| gap/embargo 付き時間分割・グループ分割（GroupKFold） | 先送り | リーク単位（同一顧客が train/valid をまたぐ等）が実データで確認された時に make_folds 系へ 1 関数 |
| ハイパラ探索（Optuna 等の自動チューニング） | 作らない（範囲外） | 変種比較（variants）で足りなくなった時に別エピックとして判断 |

---

## 10. 古典時系列（ARIMA/SARIMA/ETS）の別バックボーン経路【追記：利用者決定で「今つくる」】

前提の再確認：§4-1 の結論のうち **「sklearn 背骨に混ぜない」は維持**し、「別エピックに先送り」だけを
利用者の決定で上書きする。ML 方式（T-D＝make_time_folds／expanding／order_by）とは独立の追加であり、
時系列の第一選択は今後も ML 方式。古典側は「単変量・少数系列・季節構造そのものが主題」の実験用の第二の道具。
設計原則：DEC-0008（statsmodels をそのまま使う・翻訳層は最小）・DEC-0007（run_cv/clone を通さない別経路）・
DEC-0009（レジストリ＋docstring＋一覧＋スキル導線まで作って done）・Rule of Three（基盤化しない）。

### 10-1. モデル：statsmodels の 3 kind（全部「使う」・自作ゼロ）

| kind | 実体クラス | 必須ハイパラ | 主なハイパラ（素通し） | 安全既定（工場で焼く） |
|---|---|---|---|---|
| arima | `statsmodels.tsa.arima.model.ARIMA` | order: [p, d, q] | trend | なし（fit は既定で静か） |
| sarima | `statsmodels.tsa.statespace.sarimax.SARIMAX` | order・seasonal_order: [P, D, Q, s] | trend | `fit(disp=False)`（最適化ログを流さない＝「うるさくない」既定） |
| ets | `statsmodels.tsa.holtwinters.ExponentialSmoothing` | なし（単純平滑から） | trend・seasonal・seasonal_periods・damped_trend | なし |

- **3 kind に分ける理由**（ARIMA クラス 1 つに seasonal_order を素通しでも動くが分ける）：kind は「名前で引ける」が
  正本（§1-1 と同じ流儀）。`data models` の一覧で「季節あり＝sarima」が語彙として見え、docstring も季節周期 s の
  説明を sarima に集中できる。実体クラスも別（ARIMA / SARIMAX）なので 1 kind 1 実体の規約とも一致する。
- **seed**：ARIMA/SARIMAX/ETS の最尤推定は乱数を使わず決定的。工場は署名統一（`factory(seed, **params)`）のため
  seed を受けて捨てる（knn と同じ流儀。docstring に「乱数なし・決定的」と明記）。
- **等間隔前提**：モデルには y を **numpy の数列**として渡す（pandas index は使わない）。`order_by` は並べ替えにだけ
  使う。欠けた期間の穴埋め・再サンプリングは data 側の責務で先送り（§9）。docstring に前提を 1 行書く。
- **警告は握りつぶさない**：収束警告（ConvergenceWarning）はそのまま出す。docstring に「収束警告が出たら
  order/seasonal_order を見直すか maxiter を params で増やす」の 1 行。
- **採らない・先送り**：
  - **AutoARIMA（statsforecast）＝先送り**。依存追加（numba 系で導入が重い）に対し、次数の自動選定は当面
    「variants に order 違いを並べる」既存の変種比較で賄える（§10-4 の config 例）。復活条件は §9。
  - **Prophet＝不採用のまま**（Windows の cmdstan ビルドが壊れやすい。§4-1(b) の判断を維持）。
  - **naive / seasonal_naive の kind 登録＝先送り**（テストはテスト内で素朴予測を計算する。§9）。

### 10-2. レジストリと契約：別レジストリ `TS_MODELS` ＋ 統一契約 `ForecastLike`

**判断：MODELS に task="timeseries" で混ぜない。別レジストリにする。** 理由：

1. MODELS の kind は build_estimator（features→encode→model の Pipeline）と run_cv（clone・predict/predict_proba）に
   流れる前提がある。fit(y)/forecast(h) の物はどの経路でも壊れる（clone は get_params 前提・_predict は
   predict/predict_proba 前提）。
2. ModelEntry.task に "timeseries" を足すと、§2-3 の検査は「通るのに実行できない」組合せ
   （timeseries kind × build_estimator）を許してしまう。**別レジストリなら型レベルで交わらない**＝検査以前に事故が無い。

**置き場：新設 `src/harness/ds/forecast.py`（約 150 行・1 責務 1 ファイル）。** §0 の「新モジュールは作らない」の
例外はこの 1 つ。sklearn 背骨の pipeline.py に同居させると「混ぜない」が読み手に伝わらない。平ら構成
（ds/ 直下 1 ファイル）は維持する。モジュール冒頭 docstring に「sklearn 背骨（pipeline/cv/experiment）とは
別経路。run_cv・clone・build_estimator に載せない（DEC-0007）」を明記。

```python
# forecast.py の骨子（設計。モジュール最上部では statsmodels を import しない＝未導入でも壊れない）

@runtime_checkable
class ForecastLike(Protocol):
    """古典時系列の最小契約。fit は系列全体（過去）を受け、forecast は先の h 点を返す。exog は持たない（§9 先送り）。"""

    def fit(self, y: NDArray[np.float64]) -> "ForecastLike": ...
    def forecast(self, h: int) -> NDArray[np.float64]: ...


@dataclass
class _StatsmodelsForecaster:
    """statsmodels の薄い包み（DEC-0008：翻訳層は最小＝これ 1 クラスだけ）。

    statsmodels は構築時に y を抱く（sklearn と逆順）ので、build（y → 未学習モデル）を持ち、
    fit(y) で構築＋最尤推定、forecast(h) で結果オブジェクトの forecast を呼ぶ。それ以上のことはしない。
    """

    build: Callable[[NDArray[np.float64]], Any]
    fit_kwargs: dict[str, Any] = field(default_factory=dict)

    def fit(self, y: NDArray[np.float64]) -> "_StatsmodelsForecaster":
        self._result = self.build(np.asarray(y, dtype=np.float64)).fit(**self.fit_kwargs)
        return self

    def forecast(self, h: int) -> NDArray[np.float64]:
        return np.asarray(self._result.forecast(h), dtype=np.float64)


def _arima(seed: int, **params: Any) -> ForecastLike:
    """ARIMA（自己回帰＋差分＋移動平均）。単変量・非季節。order: [p, d, q] 必須。task: timeseries。

    等間隔の系列前提（order_by は並べ替えにだけ使う）。乱数なし・決定的（seed は受けて捨てる）。
    季節性があるデータは sarima を。収束警告が出たら order を見直すか maxiter を params で増やす。
    """
    from statsmodels.tsa.arima.model import ARIMA

    kwargs = _tuplify(params)  # order / seasonal_order を YAML の list → tuple に（変換はこの 2 キーだけ）
    return _StatsmodelsForecaster(lambda y: ARIMA(y, **kwargs))

# _sarima：SARIMAX(y, **kwargs) ＋ fit_kwargs={"disp": False}。_ets：ExponentialSmoothing(y, **kwargs)。同型。

TsModelFactory = Callable[..., ForecastLike]
TS_MODELS: dict[str, TsModelFactory] = {}
if importlib.util.find_spec("statsmodels") is not None:  # §5-2 と同じ条件登録
    TS_MODELS.update({"arima": _arima, "sarima": _sarima, "ets": _ets})


def build_ts_model(spec: Mapping[str, Any], *, seed: int) -> ForecastLike:
    """config の model 節（{kind, ...params}）から 1 つの時系列モデルを作る（build_model と同型）。

    未知 kind のエラーには statsmodels 未導入時の導入ヒント（`uv sync --extra statsmodels`）を添える。
    """
```

- **ハイパラの素通し**：params は statsmodels クラスへそのまま。唯一の変換は `order` / `seasonal_order` の
  **list → tuple**（YAML は tuple を書けない。`_tuplify` はこの 2 キー名だけを見る約 5 行。他は触らない）。
- **clone の代替**：再学習のたびに `build_ts_model(spec, seed=seed)` で**新品を工場から作り直す**
  （statsmodels は構築時に y を抱くので sklearn clone は使えない。run_forecast が窓ごとにこれをやる）。

### 10-3. 評価経路：`run_forecast`（run_cv は使わない・細い 1 関数。正本は流用のみ）

**fold 表は cv.py に `make_backtest_folds` を追加**（fold 表を作る関数の正本は cv.py に集約。
make_folds / make_time_folds と同じ (id, fold) の表形式なので、split 層への保存・再保存拒否・指紋の規律が
そのまま効く＝二重化しない）：

```python
def make_backtest_folds(df, *, order_by: str, horizon: int, n_windows: int = 1, id_column: str = "id") -> pl.DataFrame:
    """時間順バックテストの fold 割当表 (id_column, fold)。order_by で安定ソートし、末尾から horizon 行ずつ
    n_windows 個の検証窓を切る（古い窓が fold 1・最新が fold n_windows）。fold 0 ＝ 学習専用の頭。

    表の意味は expanding と同一（fold k の train ＝ fold < k の全行）なので fold_indices(how="expanding") が
    そのまま使える（T-D の成果物を流用）。決定的（seed 不要・shuffle しない）。
    order_by の重複はエラー（複数系列の混在を黙って受けない。複数系列は先送り＝§9）。
    n_windows * horizon >= 行数 もエラー（学習の頭が空になる分割は誤り）。
    """
```

**`run_forecast`（forecast.py）**：ExperimentResult / CVResult と同じ骨格の結果型で返す（train.py 側の
保存・results の作法を変えない）：

```python
@dataclass(frozen=True)
class ForecastResult:
    """バックテスト 1 回ぶんの結果。folds は split 層に保存できる（store の規律を流用）。"""

    folds: pl.DataFrame                     # (id, fold)。0=学習専用の頭・1..n_windows=検証窓
    preds: NDArray[np.float64]              # 全行の器。mask が True の行（検証窓）だけ予測が入る
    mask: NDArray[np.bool_]                 # CVResult.oof_mask と同じ規律（部分カバーを黙認しない）
    window_metrics: list[dict[str, float]]  # 窓ごとの回帰指標
    metrics: dict[str, float]               # 全検証窓を連結した回帰指標（合否判定の正本）
    passed: bool
    fitted: list[object]                    # 窓ごとの学習済み。配布用は全期間で学習し直す（雛形の作法）


def run_forecast(
    df: pl.DataFrame,
    y: NDArray[np.float64],
    spec: Mapping[str, Any],          # config の model 節。窓ごとに build_ts_model で新品を作る（clone 相当）
    *,
    order_by: str,
    horizon: int,
    n_windows: int = 1,
    seed: int,
    thresholds: Mapping[str, float],
    metrics: Sequence[str] | None = None,
    id_column: str = "id",
) -> ForecastResult:
    """時間順バックテスト：窓 k ごとに「fold < k で fit → horizon 点を forecast → 実測と比較」。

    指標は eval.evaluate_regression（rmse/mae/mape）・合否は eval.passes・fold 表は cv.make_backtest_folds
    （評価・合否・分割の正本を二重化しない）。run_cv・clone・predict_proba には触れない（DEC-0007）。
    """
```

流れ（約 40 行）：(1) order_by で安定ソート（df と y を同順に） (2) make_backtest_folds →
fold_indices(how="expanding") (3) 窓ごとに `build_ts_model(spec, seed=seed).fit(y[train]).forecast(horizon)`
(4) evaluate_regression（窓ごと＋全検証窓連結） (5) `passes(metrics, thresholds)`。

- **リーク防止が構造**：train は常に検証窓より前の行だけ（expanding の定義）。さらに forecast(h) は「先の h 点」
  しか返せない API なので、未来の情報が学習に入る経路がそもそも存在しない。
- **保存は全部流用・新規ゼロ**：fold 表 → split 層（E-0001 の save_folds と同じ作法：保存済みなら同一性確認）。
  予測表（id, fold, y, pred）→ processed 層。学習し直した最終モデル → `model_store.save_model`
  （pickle は statsmodels の results オブジェクトもそのまま入る。feature_names はダックタイピングで空になるだけ・
  TRACKED_DISTRIBUTIONS に statsmodels を足せば依存版も manifest に記録される）。results/metrics_*.yaml も同形。
- **exog は契約に入れない**（fit(y)/forecast(h) のみ）。未来の説明変数を h 期間ぶん用意する経路は config・
  データ設計を要求し、案件なしに形を決められない。SARIMAX 自体は exog を受けられるので、要る時は
  forecast.py 側の配線だけ足せばよい（§9 の復活条件）。

### 10-4. config と入口（DEC-0009：レジストリ＋docstring＋一覧＋導線）

**config の形**（実験フォルダの config.yaml。既存の語彙＝seed / data / target / thresholds / variants /
test_mode を再利用し、時系列固有は task / order_by / horizon / n_windows の 4 キーだけ）：

```yaml
task: timeseries            # 実験スクリプトが run_experiment でなく run_forecast の経路を選ぶ印
seed: 7
data: {kind: table, table_id: sales_daily}    # synthetic も可
target: y
order_by: date              # 時間順の正本（時刻・日付列）
horizon: 28                 # 先を何点当てるか
n_windows: 3                # 検証窓の数（既定 1）
model: {kind: sarima, order: [1, 1, 1], seasonal_order: [0, 1, 1, 7]}
variants:                   # 変種＝次数・モデル違い（AutoARIMA の代わりに当面これで次数を選ぶ）
  ets_weekly: {model: {kind: ets, trend: add, seasonal: add, seasonal_periods: 7}}
thresholds: {rmse: 120.0}   # 語彙は既存の回帰指標そのまま（eval への変更ゼロ）
test_mode: {n: 200, horizon: 7, n_windows: 1}
```

- **`data models` の拡張**：statsmodels 導入時のみ、MODELS の一覧の後に TS_MODELS を
  `kind\t[timeseries]\t説明 1 行目` で追記表示（T-A の task 列書式・§5 の条件登録と同じ型）。末尾の案内文に
  「[timeseries] は run_forecast 用（sklearn Pipeline には載らない）。未表示なら `uv sync --extra statsmodels`」。
  docstring 1 行目必須は test_catalog の検査対象に TS_MODELS も含める。
- **スキルは experiment スキルに追記（新 timeseries スキルは作らない）**。理由：発火語（実験・仮説・変種・比較・
  ベースライン）が完全に重なり、別スキルにすると発火が割れて片方が腐る。追記は約 6 行：
  「時間順のデータで“先の期間を当てる”のが仮説なら時系列。**第一選択は ML 方式**（`order_by:` 付き
  run_experiment ＋回帰モデル）。単変量で季節構造そのものが主題なら古典（`task: timeseries`・kind は
  `data models` の [timeseries] 群・order_by / horizon / thresholds(rmse) を config に・評価は run_forecast）」。
- **雛形（train.py）は共用しない**。sklearn 用 train.py とは流れが違う（build_estimator・stratify・閾値選択が
  無く、run_forecast＋全期間での学習し直しになる）ので、config 分岐で 1 本にすると雛形が読めなくなる。
  Rule of Three どおり **「最初の時系列実験がコピー元を作る」に留める**（E-0001 が sklearn 雛形になったのと
  同じ成り立ち）。SKILL に「E-0001 の train.py の作法（--test 必須・save_folds・results/metrics_*.yaml・
  e2e 接続）を踏襲して最小の train.py を書く」の 1 行を置く。DEC-0009 の 3 条件は
  (1) 引ける＝TS_MODELS＋`data models` (2) 分かる＝工場と run_forecast の docstring (3) 導かれる＝SKILL の追記、で満たす。

### 10-5. 依存

- **extra 名は §5-1 の規約どおりライブラリ名＝ `statsmodels`**（用途名 `timeseries` の束ね extra は作らない）：
  `statsmodels = ["statsmodels>=0.14"]`・導入は `uv sync --extra statsmodels`。
- `TRACKED_DISTRIBUTIONS`（models.py）に `"statsmodels"` を追加（保存 manifest の依存版記録。lightgbm と同じ扱い）。
- mypy overrides（pyproject）に `statsmodels.*` を追加（sklearn / lightgbm と同じ ignore_missing_imports）。
- **Windows / make 非依存を壊さない**：statsmodels は全主要プラットフォームで wheel 提供（推移依存の scipy も
  wheel）。ビルドツール不要。
- 開発・verify 環境は §5-2 の規約どおり all-extras（理由なき skip を作らない）。案件の実行環境だけ絞る。

### 10-6. テスト（期待値はすべてデータの構成から導出）

| 層 | テスト | 構成からの導出 |
|---|---|---|
| unit | カタログ検査 | TS_MODELS の全 kind に docstring 1 行目・`data models` の出力に `[timeseries]` 表記（statsmodels 導入環境）。test_catalog の検査対象に TS_MODELS を追加 |
| unit | 未導入ヒント | TS_MODELS を monkeypatch で空に → build_ts_model のエラー文に `--extra statsmodels` が含まれる（§7 の lightgbm と同型） |
| unit | list→tuple・未知 kind | `order: [1, 1, 1]`（YAML 由来の list）で fit まで通る（tuple 変換の証拠）。未知 kind は ValueError（候補一覧つき） |
| unit | 分割の入力検査 | make_backtest_folds：order_by 重複 → エラー・`n_windows*horizon >= 行数` → エラー（学習の頭が空になる分割は誤り） |
| integration | **素朴予測に勝つ** | y_t = 0.5t + 10·sin(2πt/12) + ε(σ=0.5) を n=180 で合成・h=24：sarima(seasonal_order=(0,1,1,12)) と ets(add/add/12) の rmse ＜ 季節ナイーブ（y_{t-12} の繰り返し）＜ 最終値ナイーブ。差は構成（素朴側はトレンド分を外し続ける）から導出。arima はトレンドのみのデータ（y=0.5t+ε）で最終値ナイーブに勝つ |
| integration | **バックテストの時間順（構造検査）** | 各窓で max(train の order_by) ＜ min(valid の order_by)・mask の True 数 = n_windows×horizon・検証窓に重複なし・fold 0 は評価されない（mask False） |
| integration | 決定性 | 同じ df / spec で run_forecast を 2 回 → preds が allclose・metrics 一致（最尤推定は乱数なし、の証拠） |
| integration | 合否の接続 | thresholds を緩く/きつく振って passed が向きどおり反転（rmse の higher_is_better=False は METRICS 登録済み＝eval 側の変更ゼロの証拠） |
| e2e | （T-E では作らない） | 最初の時系列実験が train.py のコピー元とともに `--test` スモークを持ち込む（§10-4・E-0001 と同じ成り立ち） |

### 10-7. 変更ファイル（T-E の範囲）

| ファイル | 変更 |
|---|---|
| `src/harness/ds/forecast.py`（新設） | ForecastLike・_StatsmodelsForecaster・工場 3 つ・TS_MODELS（条件登録）・build_ts_model・ForecastResult・run_forecast（合計約 150 行） |
| `src/harness/ds/cv.py` | make_backtest_folds（約 20 行。fold_indices(how="expanding") は T-D の成果物を流用） |
| `src/harness/cli.py` | `data models` に TS_MODELS の条件付き追記表示＋案内文 1 行 |
| `src/harness/ds/models.py` | TRACKED_DISTRIBUTIONS に "statsmodels" |
| `pyproject.toml` | extra `statsmodels`・mypy overrides に `statsmodels.*` |
| `tests/test_forecast.py`（新設）・`tests/test_catalog.py` | §10-6 のテスト・カタログ検査の対象追加 |
| `.claude/skills/experiment/SKILL.md` | 古典時系列の入口約 6 行（§10-4） |

**触らないもの（別経路である証拠）**：run_cv・experiment.py・eval.py・store.py・pipeline.py は変更ゼロ。
評価（METRICS/passes）・保存（store/model_store）・fold 表の規律は流用のみで、正本の二重化は無い。
