<!-- EP-06（実験ループ）の詳細設計。全体像→各モジュール→テスト戦略→着手順。
     移植元：draft/reference/ml-competition-template-main（MIT）。裏取り済み。
     この文書は正本。着手順は item.md と一致させること。 -->
# 段階1（EP-06）実験ループ設計書 — 特徴量→学習→評価→記録→登録

## R. 改訂：ゼロベース再設計（2026-07-03・DEC-0006/0007）

利用者の指摘（sklearn ライクな自前 Protocol は二重・個別変換は sklearn・特徴量作成の枠組み＝BaseBlock の考え方は作る・過剰分割を適切な粒度へ・エージェントファースト）を受けた改訂。**以下 R が正本。旧 B-2/B-4/D-2/D-3/D-4 はこれで置き換わる**。

**背骨は sklearn の Pipeline。** 特徴量→モデルを1本の `sklearn.pipeline.Pipeline` にし、CV の fold ごとに `sklearn.base.clone` して train 側だけで fit する。**漏れ防止は「規約」でなく「構造」**（clone された Pipeline が train でだけ fit するので valid の統計が混ざる経路が無い）。個別の標準変換（StandardScaler・OneHotEncoder 等）は sklearn を直接使い、自作しない。ハーネスが足すのは sklearn の外の薄い層だけ。

**捨てる自前抽象**：`TargetTransform`/`Identity`/`Log1p`/`StandardScale`（＝`TransformedTargetRegressor`＋`StandardScaler`／`FunctionTransformer(np.log1p, np.expm1)` の焼き直し。transforms.py 削除）。`Trainer`/`FoldOutcome`/`SklearnTrainer`（＝sklearn estimator＋`clone` の焼き直し。train.py は作らない）。

**作る特徴量枠組み（BaseBlock の考え方・モデル非依存）**：`features.py`。
- `FeatureBlock(BaseEstimator, TransformerMixin)`：特徴量作成の1単位の基底。polars 入→polars 出・名前付き出力列・`get_feature_names_out`・`describe`。sklearn 互換なので `clone` でき Pipeline に入る。**個別の標準変換のブロックは作らない**（StandardScaler 等は sklearn を直接 ColumnTransformer/Pipeline に入れる）。作るのは「モデルに依らない特徴量ロジック」（交互作用・集約など複数列から作る本物の特徴量）だけ。段階1の具体は `Interactions(pairs)`（`a_x_b` 列）1つ。
- `FeaturePipeline`：ブロック（と必要なら sklearn transformer）を横に束ねる薄い sklearn 互換 transformer。`fit/transform/get_feature_names_out/describe`。検査＝行数不変・出力列名の重複禁止（人にもエージェントにも「どの特徴量がどこから来たか」を describe で示す）。これを estimator Pipeline の `"features"` 段に入れる。

**一気通貫の薄い接着**：`experiment.py`。`build_estimator(spec, model)`（config の特徴量指定＋モデルから Pipeline を組む）と `run_experiment(...)`（load→make_folds→store.save(split)→run_cv→eval.passes→store.save(OOF)→save_model→results）。実験の `code/train.py` はこれを呼ぶだけ（＝二重実装を避けつつ端から端まで1関数で追える）。

**残すハーネス固有**（sklearn の外・自作が正当）：`data.py`（合成・id ハッシュ固定分割）／`schema.py`＋`store.py`（テーブル定義・config URI 保存・指紋・manifest・split 再保存拒否）／`cv.py`（fold 表＋`run_cv` の clone-per-fold 約40行。sklearn に「1回で OOF＋mask＋fold 別 estimator＋指標」を返す口が無い）／`eval.py`（sklearn.metrics＋passes＋閾値選択）／`models.py`（Pipeline 丸ごと保存・版・指紋・台帳・昇格）／実験構造（SPEC・--test・verify）。

**モジュール構成（適切な粒度・エージェントファースト。参考リポの過剰分割はしない）**：`src/harness/ds/` を平らな8ファイルに——`data.py`／`schema.py`／`store.py`／`features.py`／`cv.py`／`eval.py`／`models.py`／`experiment.py`。各ファイル＝1責務・名前で引ける。blocks/ サブパッケージや training/ の細分化はしない。

**着手順（改訂・全体→詳細）**：T-0017（済）→ ①transforms.py 削除 → ②cv.py 作り直し（`run_cv(estimator,…)`・clone-per-fold・`Trainer` 削除）→ ③features.py（FeatureBlock/FeaturePipeline/Interactions）→ ④experiment.py＋E-0001 骨組み（baseline を `--test` で一気通貫・e2e を verify に接続）→ ⑤eval 閾値選択 → ⑥models.py → ⑦E-0001 完了。T-0013 は features.py（BaseBlock の考え方・sklearn 互換）として作る。T-0015 は sklearn estimator＋clone で代替のため廃止（ID 再利用しない）。

**run_cv の署名（改訂）**：
```python
def run_cv(estimator, x: pl.DataFrame, y, splits, *, predict="proba", metric_fn=evaluate) -> CVResult:
    # fold ごとに clone(estimator).fit(train部) → valid を予測して oof に格納。
    # CVResult(oof, oof_mask, fold_metrics, estimators, oof_metrics)。valid 重複は失敗。
```
テストは `FakeTrainer` を廃し **sklearn の `DummyClassifier`** を使う。漏れ検知は `Pipeline([("sc",StandardScaler()),("m",DummyClassifier())])` を run_cv に通し `estimators[k].named_steps["sc"].mean_` が train 部の平均と一致すること（train 統計だけで fit した証拠）で確かめる。

---

## A. 全体像（※R で改訂。以下は初版の記録）

新規モジュールはすべて `src/harness/ds/` に置く（eval.py への追記1件＋新規4件）。データの表（polars DataFrame）はテーブル定義・保存・fold 表・特徴量の入出力までで使い、学習の数値計算（行列 X・目的 y・予測・指標）は numpy 配列だけで行う。境界は「FeaturePipeline の出力を `.to_numpy()` した瞬間」の1か所に固定する。学習系（cv.py / train.py）は store を import しない（保存は実験スクリプトの仕事）。依存の向きは一方通行：`実験スクリプト → cv/train/features/eval/models → transforms/eval(数値) → numpy` と `実験スクリプト → store/schema → config`。乱数は全関数で `seed` 明示引数、グローバル種設定は使わない（参考リポの `set_seed` は非採用を維持）。

```
store.load(raw)                       … polars。テーブル定義で検証済みのデータ
   │
   ├─ cv.make_folds(df, n_folds, seed, stratify_by)  → fold表 (id, fold)
   │      └ store.save(fold表, split層)   … 再書き込み拒否＝分割の再現をデータで担保
   │
   ├─ cv.fold_indices(df, fold表)  → [(train_idx, valid_idx)] × k   … 添字対のリスト
   │
   ├─ features.FeaturePipeline.fit_transform(train部) / transform(valid・test部)
   │      └ .to_numpy() ──────────── ここから numpy ────────────
   │
   ├─ cv.run_cv(X, y, splits, trainer, seed=…, metric_fn=eval.evaluate)
   │      └ trainer.train(X_tr, y_tr, X_va, y_va, seed=fold毎の種) → FoldOutcome
   │      → CVResult(oof, oof_mask, fold_metrics, models, feature_names)
   │
   ├─ eval.select_threshold_max_f1(y_oof_true, oof)   … 閾値は OOF/valid でだけ選ぶ
   ├─ eval.evaluate(...) → eval.passes(metrics, thresholds) → 終了コード
   │
   ├─ store.save(OOF・予測の表, processed層)           … 指紋つき manifest
   └─ models.save_model(model, data_fingerprint=…)    … pickle＋manifest・上書き拒否・台帳
```

## B. モジュール詳細設計

### B-1. eval.py への追記（T-0012 閾値選択）— sklearn.metrics を使う

閾値選択も `sklearn.metrics`（`precision_recall_curve` / `f1_score`）で実装する（再発明しない・参考リポ `domain/threshold.py` と同じ）。`precision_recall_curve` は各「distinct なスコア」を閾値候補として返すので、格子探索より正確で、テストの期待値も入力の構成から厳密に導ける。ハーネス固有なのは「valid/OOF で選ぶ・train/test で選ばない」という**使い方の規約**だけ（下の関数名と docstring がそれを担う）。

```python
def f1(y_true: NDArray[np.int_], y_pred: NDArray[np.int_]) -> float:
    """F1（陽性側）。陽性の予測も正解も無いときは 0.0。"""

def select_threshold_max_f1(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64]
) -> tuple[float, float]:
    """F1 を最大にする閾値を y_score の一意な値から選ぶ。返り値は (閾値, そのときの F1)。
    同点のときは大きい方の閾値（陽性を控えめに出す方）。
    ※ 閾値は valid か OOF の予測で選ぶこと。train で選ぶと過大評価、test で選ぶと漏れ。"""

def select_threshold_at_recall(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, target: float
) -> float:
    """再現率 ≥ target を満たす最大の閾値。満たせなければ min(y_score)（全部陽性）。"""

def select_threshold_at_precision(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, target: float
) -> float:
    """適合率 ≥ target を満たす最小の閾値。満たせなければ max(y_score) より大（全部陰性）。"""
```

- Youden's J 版（optimize_threshold_roc）は取り込まない。F1 最大・recall/precision 指定の3つで段階1の用途は足りる。必要になった実験で足す。
- `get_threshold_metrics` 相当は既存 `evaluate(y_true, y_score, threshold=...)` がそのまま担う（新設しない）。
- 実装は `sklearn.metrics.precision_recall_curve` に委譲（distinct なスコアごとの precision/recall/threshold を得て、f1 最大・recall/precision 指定をその配列から選ぶ）。手書きの TP/FP 集計はしない。

### B-2. features.py（T-0013）— FeatureBlock Protocol＋FeaturePipeline

参考リポとの差分：`BaseBlock`（継承ベース・`fit()` が変換結果を返す紛らわしい設計・`set_seed` 同居）はやめ、**Protocol＋fit_transform 第一級**にする。OOF 型ブロック（target encoding 等）で `fit_transform(train) ≠ transform(train)` になり得ることを契約として明文化する（核1）。

```python
@runtime_checkable
class FeatureBlock(Protocol):
    """特徴量ブロックの契約。統計の学習は train 側でだけ起きる。

    - fit_transform: train を受け、必要な統計を学習して変換結果を返す。
    - transform: 学習済みの統計だけで変換する（valid・test 用。統計を更新しない）。
    - OOF 型のブロックでは fit_transform(train) と transform(train) は一致しなくてよい。"""
    def fit_transform(self, df: pl.DataFrame, y: NDArray[np.float64] | None = None) -> pl.DataFrame: ...
    def transform(self, df: pl.DataFrame) -> pl.DataFrame: ...

class FeaturePipeline:
    def add(self, name: str, block: FeatureBlock, *, description: str = "") -> FeaturePipeline: ...
    def fit_transform(self, df: pl.DataFrame, y: NDArray[np.float64] | None = None) -> pl.DataFrame: ...
    def transform(self, df: pl.DataFrame) -> pl.DataFrame: ...
    def feature_names(self) -> list[str]: ...
    def describe(self) -> list[dict[str, object]]:  # name / output_columns / description
```

パイプラインが機械的に守らせる検査（参考リポには無い。全部 ValueError/RuntimeError）：
- 各ブロックの出力行数 ＝ 入力行数（行がずれた特徴量の混入を止める）。
- ブロック間で出力列名の重複禁止（horizontal concat 前に検査）。
- `transform` を `fit_transform` より先に呼んだら失敗。
- `transform` の出力列が fit 時と（順序含め）一致しなければ失敗（列順ずれ＝行列の列ずれを止める）。

同梱する汎用ブロックは3つだけ（列名は引数で渡す＝案件固有に寄せない）：
- `ColumnsBlock(columns: Sequence[str])` … 素通し選択（無状態）
- `InteractionBlock(pairs: Sequence[tuple[str, str]])` … 積の特徴量 `a_x_b`（無状態。E-0001 の主役）
- `StandardScaleBlock(columns: Sequence[str])` … fit で平均・標準偏差を学習（有状態・漏れ検知テストの被験体）。標準化は `sklearn.preprocessing.StandardScaler` に委譲する（再発明しない）

blocks サブパッケージは作らない（EP-06 の「やらないこと」どおり、実験駆動で features.py に足し、増えたら分割）。

### B-3. cv.py（T-0014）— fold 表・添字対・run_cv

分割そのものは sklearn の `KFold`/`StratifiedKFold`（shuffle・random_state=seed）を使う（再発明しない）。参考リポとの差分は「隠れ既定 `random_state=42` を持つ包み `CVSplitter`」や `create_cv_splitter(config)` 工場を作らない点と、**fold 割当をデータ（split 層テーブル）にして再現をデータで担保する**点（核2）。make_folds はその sklearn の分割結果を (id, fold) 表に落とすだけ。

```python
def make_folds(
    df: pl.DataFrame, *, n_folds: int, seed: int,
    id_column: str = "id", stratify_by: str | None = None,
) -> pl.DataFrame:
    """fold 割当表 (id_column, fold) を作る。純 numpy 実装：
    - 無層化: rng.permutation の並びを n_folds に等分（各 fold の行数差は高々1）。
    - 層化: stratify_by の値ごとにシャッフルし fold = 順位 % n_folds
      （各 fold 内のクラス件数差は クラスごとに高々1）。
    同じ (df, seed) なら同一の表。"""

def fold_indices(
    df: pl.DataFrame, folds: pl.DataFrame, *, id_column: str = "id"
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """fold 表を df の行番号の対 [(train_idx, valid_idx)] × k に引き直す。
    df に fold の無い id・表に無い id があれば失敗（部分適用の黙認をしない）。"""

def holdout_indices(n_train: int, n_valid: int) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """固定分割用。train を先頭・valid を後ろに連結した行列を前提に、要素1のリストを返す。
    固定分割も CV も「添字対のリスト」で学習系へ渡す形を揃える（核2）。"""

@dataclass(frozen=True)
class CVResult:
    oof: NDArray[np.float64]          # 全行ぶんの器。覆われた行だけ意味を持つ
    oof_mask: NDArray[np.bool_]       # 予測が入った行（CV=全True・固定分割=valid行だけTrue）
    fold_metrics: list[dict[str, float]]
    models: list[object]
    oof_metrics: dict[str, float]     # mask の行だけで計算

def run_cv(
    X: NDArray[np.float64], y: NDArray[np.float64],
    splits: Sequence[tuple[NDArray[np.int64], NDArray[np.int64]]],
    trainer: Trainer, *, seed: int,
    metric_fn: Callable[[NDArray[np.int_], NDArray[np.float64]], dict[str, float]] = evaluate,
) -> CVResult:
    """fold ごとに trainer.train を呼び、valid への予測を oof[valid_idx] に格納。
    fold の種は np.random.SeedSequence(seed).spawn(k) から導出（fold 間で独立・再現可能）。
    valid_idx が重複していたら失敗（同じ行に2回書く分割は分割の誤り）。"""
```

参考リポの `runner.py` は `oof = np.zeros(len(y))` で未カバー行が黙って 0 になる。**oof_mask の追加**がこれへの修正で、固定分割（要素1）でも同じ関数が正しく使える。cv.py は store を import しない（保存は実験スクリプト側。テストで往復を結線）。

### B-4. train.py（T-0015）— SklearnTrainer（Trainer/FoldOutcome は cv.py に）

参考リポとの差分：`train_fold` に seed が無く、乱数はモデルパラメータ任せ（暗黙）。**seed を train の明示引数**にする（核3）。また target_transform（T-0011 の成果）をここで結線する。
**契約の置き場（実装で確定）**：`Trainer` Protocol と `FoldOutcome` は消費側の `cv.py` に置く（run_cv が使う・cv→train の循環を避ける）。train.py の `SklearnTrainer` は `from harness.ds.cv import Trainer, FoldOutcome` を実装する。

```python
@dataclass(frozen=True)
class FoldOutcome:
    y_pred: NDArray[np.float64]                      # valid への予測（必ず元スケール）
    model: object
    feature_importance: NDArray[np.float64] | None = None

@runtime_checkable
class Trainer(Protocol):
    def train(
        self,
        X_train: NDArray[np.float64], y_train: NDArray[np.float64],
        X_valid: NDArray[np.float64], y_valid: NDArray[np.float64],
        *, seed: int,
    ) -> FoldOutcome: ...

class SupportsFitPredict(Protocol):
    """sklearn 互換の最小契約（fit と predict。分類器は predict_proba も可）。"""
    def fit(self, X: NDArray[np.float64], y: NDArray[np.float64]) -> object: ...
    def predict(self, X: NDArray[np.float64]) -> NDArray[np.float64]: ...

class SklearnTrainer:
    def __init__(
        self,
        model_factory: Callable[[int], SupportsFitPredict],   # seed → モデル。例 lambda s: LogisticRegression(random_state=s)
        *,
        target_transform: TargetTransform | None = None,      # 変換して学習し、予測は必ず inverse で戻す
        predict: Literal["proba", "value"] = "value",         # 分類は "proba"（predict_proba[:,1]）
    ) -> None: ...
    def train(self, X_train, y_train, X_valid, y_valid, *, seed: int) -> FoldOutcome: ...
```

重要な点：**train.py 自体は sklearn を import しない**。モデルは呼び出し側が `model_factory` で注入する（ダックタイピング＋Protocol）。だから核となる src は sklearn 無しで型検査・テストが通り、LightGBM への移行は「factory と Trainer 実装を差し替えるだけ」の一本道になる（核3の移行路）。`target_transform` の fit（StandardScale）は **y_train でだけ**行う（valid の統計を混ぜない）。

### B-5. models.py（T-0016）— 永続化と登録簿（`harness/ds/models.py`）

**設計の芯**：pickle を「形式の既定」から「native 形式を持たないオブジェクトのための最後の受け皿」に格下げする。直列化そのものは呼び出し側が注入する `Serializer`（Protocol）に追い出し、核（models.py）には**封筒だけ**を残す——URI 解決・版採番・原子的書き込み・上書き拒否・指紋・依存版の記録と照合・manifest・台帳（生成ビュー）・昇格の関門。これで核は sklearn/LightGBM/onnx を一切 import しないまま、形式が何であっても store.py と同じ規律で保存・読込・登録できる。保存は常に許し（実験の記録）、**昇格だけ**をベースライン比較の関門にする（登録と合格を分ける＝「負の結果も記録で完了」と両立）。参考リポ2本の実務（本体は native/ONNX・pickle は限定・依存版を記録・レジストリは (model,version) キー・登録＝関門）を我々の流儀へ翻訳したもの。

`harness/models.py`（PM の Item 型）と同名なので import は `from harness.ds import models as model_store` の別名規約で混同を防ぐ。

**(1) Serializer — 形式固有の処理はここだけに閉じる**
```python
@runtime_checkable
class Serializer(Protocol):
    """モデル実体の直列化の契約。形式固有の import はこの実装の中だけ。
    format: manifest に記録し load 時に取り違えを検査。extension: format と対（自己記述性）。
    critical: load 互換に効く配布物名（例 ("scikit-learn","numpy")）。save 時に版を記録し load 時に照合。"""
    format: str; extension: str; critical: tuple[str, ...]
    def dump(self, model: object, path: Path) -> None: ...
    def load(self, path: Path) -> object: ...

@dataclass(frozen=True)
class PickleSerializer:  # 核に置く唯一の実装。stdlib pickle なので境界を破らない
    format: str = "pickle"; extension: str = "pkl"; critical: tuple[str, ...] = ("numpy",)
```
LightGBM native（`booster.save_model(.txt)` を包む約10行）や ONNX は、核から import されない別モジュール／実験 code に置く。

**(2) Trainer との噛み合わせ**（Trainer Protocol は変えない。直列化は別の関心）
```python
@runtime_checkable
class SerializerProvider(Protocol):
    def serializer(self) -> Serializer: ...   # 自分のモデルに合う Serializer を知る Trainer が任意で実装
```
`SklearnTrainer.serializer()` は `PickleSerializer(critical=("scikit-learn","numpy"))` を返す（文字列を返すだけ＝train.py は sklearn 非 import を維持）。実験雛形の定型：`ser = trainer.serializer() if isinstance(trainer, SerializerProvider) else PickleSerializer()`。※ モデル自身に save/load を強いる継承方式（参考リポ B の BaseModel）は非採用（sklearn オブジェクトを包めない・注入の方が本基盤と揃う）。

**(3) 記録・保存・読込**
```python
@dataclass(frozen=True)
class ModelRecord:
    name: str; work: str; version: str            # version = UTC "%Y%m%dT%H%M%S%fZ"（辞書順＝時刻順）
    path: Path; format: str; filename: str        # 実体ファイル名（拡張子込み・自己記述）
    fingerprint: str                              # 実体の sha256
    pipeline_filename: str | None; pipeline_fingerprint: str | None  # 前処理器を同梱したとき
    feature_names: tuple[str, ...]                # 列順（推論時の列ずれ検知の材料）
    data_fingerprint: str | None                  # store.save の返り値と結ぶ
    metrics: dict[str, float]; config: dict[str, object]  # 変種名・seed・n_folds 等
    code: str | None                              # 実行体パス（git 不使用のため）
    python: str; critical_dependencies: dict[str, str]    # 照合対象の name→版
    dependencies: dict[str, str]                  # 全配布物 name→版（記録のみ・再現材料）
    created: str

def save_model(root, model, *, name, work, serializer=None, pipeline=None, feature_names=(),
               data_fingerprint=None, config=None, metrics=None, code=None) -> ModelRecord:
    """封筒だけ：版を採番し serializer.dump で一時ファイル→rename、sha256 と依存版
    （importlib.metadata）を集め manifest.yaml を書く。pipeline を渡せば同じ経路で同梱。
    置き場 <uri_for("models")>/work/<work>/models/<name>/<version>/{model.<ext>, pipeline.pkl, manifest.yaml}。
    再 save は新しい版として積む。同じ版が在れば ValueError。file: 以外は NotImplementedError。"""

def load_model(root, *, name, work, version=None, serializer=None,
               on_dependency_mismatch: Literal["warn","fail"]="warn") -> LoadedModel:  # (model,pipeline,record)
    """3段の門：①完全性=manifest 無し・sha256 不一致は常に fail。②形式=serializer.format≠manifest は常に fail
    （.txt を pickle で読む取り違えを止める）。③互換性=critical_dependencies と python を照合、既定 warn
    （on_dependency_mismatch="fail" で強化）。version=None は最新（版の降順1件）。"""
```

**(4) 登録簿（台帳＝生成ビュー・backend 差し替え口）**
```python
@runtime_checkable
class ModelRegistry(Protocol):        # file: 以外（S3+DynamoDB 等）はこれを実装して差し替える
    def get(self, *, work, name, version) -> ModelRecord: ...
    def latest(self, *, work, name) -> ModelRecord | None: ...
    def list(self, *, work=None, name=None) -> list[ModelRecord]: ...
    def champion(self, *, work, name) -> ModelRecord | None: ...

class FileRegistry:  # file: backend。manifest 群の走査＝台帳（1本の JSON 台帳は作らない＝正本を2重化しない）
    def __init__(self, root: Path) -> None: ...  # latest は版文字列の降順1件（辞書順＝時刻順）

def list_models(root, *, work=None) -> list[ModelRecord]:  # FileRegistry を包む薄い関数。CLI `uv run data models`（champion に印）
```
backend は `config.data.uri_for("models")`（層の上書き口をそのまま使う・既定 `file:data`＝設定変更ゼロで動く）。`file:` 以外は NotImplementedError（store.py と同一作法）。

**(5) 昇格＝ベースライン比較の関門**
```python
def promote_model(root, *, work, name, version, thresholds, primary, higher_is_better=True) -> Promotion:
    """両方通ったときだけ昇格：①絶対関門 eval.passes(record.metrics, thresholds) が True。
    ②相対関門 現 champion が無ければ無条件・在れば primary で勝つ。通れば
    models/<name>/promotions/<decided>.yaml を追記（追記のみ）。champion＝最新の昇格記録が指す版（生成ビュー）。
    落ちたら両者の指標を載せて ValueError。save_model は常に許す＝実験の記録。関門は昇格だけ。"""
```
```
data/work/<work>/models/<name>/
├── 20260703T093000123456Z/  model.pkl  pipeline.pkl  manifest.yaml
├── 20260703T110412987654Z/  model.pkl  pipeline.pkl  manifest.yaml
└── promotions/20260703T111000000000Z.yaml   # 追記のみ。最新が champion を指す
```

**pickle 緩和策（参考リポの「記録のみ」より一段安全に）**：①依存版を全量記録（再現材料）。②load 時照合は `serializer.critical`＋python に限定（全量はノイズ）・既定 warn（uv.lock で環境は固定済み・fail 既定だと patch 版上がりで台帳が死蔵）・完全性と形式は常に fail（「壊れ・取り違え」と「環境が進んだ」を同じ強さにしない）。③自己記述性＝manifest に format・filename・指紋を必ず持ち load は名から引く（参考リポ B の「native なのに .pkl」を構造的に防ぐ）。④pickle は「自分が書いた manifest 付きファイルだけ読む」（sha256 が裏付け）。

**既存資産との接続**：store.py（URI 解決・rename・指紋・manifest の4作法を踏襲、`data_fingerprint` は `store.save` の返り値）／Trainer は無変更＋`SerializerProvider` 追加で sklearn 非 import を維持／`eval.passes` が昇格の絶対関門（実験の合否と昇格が同じ関数・同じ thresholds 節）／`FeaturePipeline` を `pipeline=` で同梱・`feature_names()` で列順記録／pm・issues と同型（事実はファイル・台帳は生成ビュー・追記のみ・ID/版は再利用しない）。**models.py の import は stdlib＋yaml＋harness.config のみ（numpy すら不要）＝境界維持を import 一覧で機械確認できる。**

### B-6. E-0001 実験フォルダ（雛形＝以後の実験の正本）

```
work/EP-06-ds-experiment-loop/E-0001-interaction-feature/
├── item.md          # kind: experiment・仮説1つ・depends_on・verified_by: tests/test_e2e_experiment.py::test_e0001_smoke
├── SPEC.md          # 仮説・判定基準（どの指標がいくつ動いたら採択）・データ・手順
├── config.yaml      # 下記
├── data/            # e0001_folds.yaml (split層) / e0001_oof.yaml (processed層・role: prediction)
├── code/train.py    # 唯一の実行体。--variant / --test / --root
└── results/         # metrics.yaml（変種別指標・選んだ閾値・データ指紋・モデル指紋）
```

```yaml
# config.yaml — 変種は config で持つ（実験＝1仮説）
seed: 20260703
n: 2000
n_folds: 5
variants:
  baseline:    {features: [columns]}
  interaction: {features: [columns, interaction]}
test_mode: {n: 240, n_folds: 3}       # --test のときの規模
thresholds: {roc_auc: 0.80}           # 値は人の判断待ち（F 参照）
```

`code/train.py` の流れ（A のデータフローそのまま）：`--root`（既定＝リポ根）配下で generate_synthetic → store.save(raw) → make_folds → store.save(split) → store.load ＋ fold_indices → FeaturePipeline（config の features 節から組む）→ run_cv(SklearnTrainer(LogisticRegression)) → select_threshold_max_f1(OOF) → evaluate/passes → store.save(OOF表) → save_model → results/metrics.yaml。**`--test` は tempfile の一時ディレクトリを root にして全部そこで行う**（conftest の Project と同じ構成を組み、data/ の表定義をコピー）。これで「split 層は再書き込み拒否」の規律と `--test` の何度でも実行が両立し、リポも汚れない。

## C. テスト戦略

### ピラミッド表

| 層 | 対象 | 代表テスト | 合否の根拠数値（テストデータの構成から導出） | マーカー |
|---|---|---|---|---|
| unit | eval 閾値選択 | `test_select_threshold_max_f1` | y=[0,0,1,1], s=[.1,.4,.6,.9] → F1=1.0 になる閾値域は (0.4, 0.6]。候補＝一意スコアなので返り値は厳密に 0.6・F1==1.0 | unit |
| unit | eval 閾値選択 | `test_select_threshold_at_recall` | 同データ target=1.0 → 両陽性を拾う最大閾値＝0.6（厳密一致） | unit |
| unit | cv.make_folds | 割当の均等・層化・決定性 | n=20, k=4 → 各 fold ちょうど5行。y が 8:12 の層化 → 各 fold 陽性2・陰性3。同 seed 同表・異 seed 別表 | unit |
| unit | features | 行数・列重複・未fit・列順の防御 | 行を1行落とすブロック→ValueError。同名列2ブロック→ValueError。transform 先行→RuntimeError | unit |
| unit | models | 往復・拒否 | save→load で predict 同値。同名 save 2回目→ValueError。manifest 削除後 load→ValueError。pkl 改変後 load→ValueError | unit |
| integration | run_cv×FakeTrainer（結線） | `test_run_cv_wiring` | Fake は fold f で定数 (f+1)/10 を返す。k=3, n=30 → train 呼び出し3回・oof_mask.sum()==30・oof[fold f の valid行]==(f+1)/10 厳密一致・fold_metrics 長さ3。渡した seed が fold 間で異なることも記録で確認 | integration |
| integration | run_cv×固定分割 | `holdout_indices` 経由 | 要素1 → oof_mask.sum()==n_valid、train 呼び出し1回 | integration |
| integration | fold 表の往復 | make_folds→store.save(split)→load→fold_indices | 往復前後で添字対が完全一致。同 table_id への再 save→ValueError（split 層の規律） | integration |
| integration | 特徴量の漏れ検知 | `test_no_valid_stats_in_train` | train x を平均0・標準偏差既知に厳密構成、valid = train+10。StandardScaleBlock fit_transform(train) 後の transform(valid).mean()==10/std（train 統計を使った証拠）。漏れて valid で fit していたら 0 になる——値は構成から厳密に導出 | integration |
| integration | SklearnTrainer 再現性・target_transform | 同 seed 2回で予測が allclose。StandardScale は y_train だけで fit（valid の y を書き換えても予測不変） | 予測の同値性＝構成由来（同入力同種） | integration |
| e2e | E-0001 `--test` スモーク | `test_e0001_smoke`（subprocess で `code/train.py --test --variant baseline` 実行） | 終了コード0。results/metrics.yaml・OOF parquet・model pkl＋manifest が存在。oof_mask 全行。roc_auc ≥ 0.8 —— 根拠：y は 1.5x1−2x2＋雑音(std 0.5) の符号で決まり、信号の標準偏差 2.5 に対し雑音 0.5（信号:雑音=5:1）。真のロジットの AUC は約0.97 で、線形モデルが 0.8 を下回るのはデータ構成上あり得ない | e2e |
| e2e | 変種の切替 | `--variant interaction --test` も終了コード0・同じ成果物 | 同上 | e2e |
| slow | E-0001 本規模（n=2000, k=5）実行と baseline/interaction 両変種の比較記録 | 実行が通り results が揃うことのみ検証（優劣は仮説の答えなので断定しない） | slow, e2e |

統合テスト用の **FakeTrainer は tests/ 内に置く**（src に置くと本番コードと紛れる）。`Trainer` Protocol を満たす約20行のクラスで、呼び出し記録（回数・受け取った seed・行数）を持つ。

### 検証の仕組み：段階（level）×テストの目印（marker）— テンプレートに組み込む

これは土台（テンプレート）の一部として最初から作り込む。今のテスト数が少ないことは理由にしない。この repo を土台にする全案件が、初めから「速い内側ループ＋端まで確かめる門番＋切り離せる重い層」を得る。

**2つの軸**：
- **段階（level・`checks.toml`）＝その瞬間に見合う検査**：fast（編集中・hook 相当）→ standard（コミット前）→ full（完了判定・CI＝`uv run verify`）。段階は累積（full は fast・standard の中身も含む）。
- **目印（marker・テスト1件ごと）＝テストの重さと範囲**：`unit` / `integration` / `e2e`（ピラミッド。**各テストにちょうど1つ**）＋ `slow`（重いものに追加で貼るフラグ）。

**対応（門番の段階は slow を絶対に含めない）**：

| 段階 | いつ | 走る検査 |
|---|---|---|
| fast | 保存・編集中 | ruff format/check ＋ `pytest -q -m "unit and not slow"` |
| standard | コミット前 | ＋ mypy ＋ `pytest -q -m "integration and not slow"` |
| **full**（＝verify・done 判定） | 完了・CI | ＋ `pytest -q -m "e2e and not slow"` |
| （段階に載せない） | 実験完了・夜間 | `pytest -q -m slow`（明示的に叩く。門番ではない） |

各段階の pytest は互いに素な目印を選ぶので二重実行にならず、**full まで通せばピラミッド全段（unit＋integration＋e2e スモーク）が走る**＝パイプラインが端から端まで動くことを毎回の done 判定で確かめる。除くのは slow（本規模の重複）だけ。

**原則**：
- 速い・高信号の検査ほど頻繁に（下の inner loop）。重い・全体の検査は門番（full）に。
- **slow は「正しさ」でなく「本規模での確信」を足すだけ**。correctness は小さい `--test` の e2e スモークが門番で担保するので、slow は門番から外して別経路（夜間 CI か実験を done にする時）に回せる。どちらに回すかは運用の選択で、仕組み（門番から外せること）は今作り込む。
- **どのテストも必ずピラミッドの目印を1つ持つ**。付け忘れ＝どの段階でも走らない“迷子テスト”を防ぐため、**未マークのテストは失敗**にする機械ガードを置く（`conftest.py` の `pytest_collection_modifyitems` で、unit/integration/e2e のいずれも無い item を collect エラーにする）。`--strict-markers`（未登録マーカーを弾く）と対で「無印」も塞ぐ。

**e2e→verify の接続（この仕組みの帰結）**：
- e2e テストは実験スクリプト**そのもの**を subprocess で叩く（`sys.executable` ＋ `--test --root <tmp>`）。「雛形から乖離した実験」「テストだけ通る二重実装」が構造的に不可能になる——full が落ちるのはスクリプト本体が壊れたとき。
- E-0001 の `verified_by: tests/test_e2e_experiment.py::test_e0001_smoke`。既存 pm.lint（`::名` の実在検査・done 実験の results/ 必須）にそのまま噛み合う。
- 追加の機械ガード（**後で足す**・G 節「後で足す分」）：`work/**/code/*.py` に `np.random.seed` / `random.seed` を含んだら error にする検査。当面はグローバル種の禁止を AGENTS のレビュー観点で担保し、追って機械強制に上げる。

**この仕組みを組み込む作業（T-0017 として先に入れる）**：(1) `checks.toml` の各段階 pytest を上表の marker 選択にする、(2) 既存テスト8ファイルに `pytestmark` でピラミッドの目印を付ける（分類は下のピラミッド表の「マーカー」列）、(3) 未マーク失敗ガードを conftest に置く。これは ML モジュールに依存しないので、歩く骨組み（T-0014）より前に置ける。

## D. 横断的な設計判断

**D-1. sklearn は ds の一級依存。標準の数値・分割・スケーリングは sklearn を使う（再発明しない）。ただしモデルの具体と直列化は注入して差し替え可能に保つ。**（当初の「核は sklearn 非 import」から反転。DEC-0006・L-007）
- pyproject の ds extra に `scikit-learn>=1.6`、mypy overrides に `sklearn.*` を追加。
- 使う所：eval のメトリクス（`accuracy_score`/`roc_auc_score`…）、`cv.make_folds`（`KFold`/`StratifiedKFold`）、`transforms.StandardScale`（`StandardScaler`）、threshold（`sklearn.metrics`）。手書きの数値・分割・スケーリングは置かない（保守負債・バグの温床。参考リポも全メトリクスを sklearn 実装）。Log1p/Identity は numpy 標準関数そのものなので追加ライブラリ不要。
- 差し替えを保つ境界：**モデルの具体**（LogisticRegression/LightGBM 等）は Trainer の `model_factory` で注入し train.py は特定モデルライブラリを import しない。**直列化の形式**は Serializer で注入し models.py は形式ライブラリを import しない。これで sklearn→LightGBM の移行を一本道に保ちつつ標準実装の恩恵を受ける。
- 標準が例外を投げる縁（単一クラスの AUC 等）だけハーネスの方針で吸収（`roc_auc` は 0.5 を返す）。

**D-2. numpy/polars の境界は1点。** polars＝表とメタデータの世界（store/schema/fold表/FeatureBlock）、numpy＝学習の数値の世界（X, y, oof, 指標, 変換）。変換は `FeaturePipeline` の出力 DataFrame を `.to_numpy()` する1か所だけ。列順は `feature_names()` で記録し、モデル manifest の config に残す（推論時の列ずれ検知の材料）。

**D-3. fold ごとの種は SeedSequence で導出。** `run_cv` は受け取った seed から `np.random.SeedSequence(seed).spawn(k)` で fold 別の種を作り、`trainer.train(..., seed=fold_seed)` に渡す。呼ぶ場所で決めた種だけが効く、という AGENTS の規約と一致。

**D-4. 特徴量の fit は「学習に使う行」でだけ行う。** 段階1の run_cv は行列 X を受け取る設計（計画どおり）で、特徴量は CV の前に作る。これが漏れなしで成り立つのは段階1のブロックが無状態（Columns/Interaction）または固定分割の train でだけ fit する使い方だから。**fold 内 fit が必要な有状態ブロック（target encoding 等）を導入する時が `run_cv_with_features(...)` を足す時**——この境界条件を features.py の docstring に明記し、先回りの複雑化はしない。

**D-5. mypy の範囲は src・tests のまま。** work/ の実験コードは変更が激しく、型検査は ruff（`.` 全体）＋e2e スモークで担保する。実験コードが src に昇格する時に strict の対象になる。

**D-6. 参考リポで非採用を確認したもの（裏取り済み）：** `features/base.py set_seed`（グローバル種）／`cv.py` の `random_state=42` 隠れ既定と sklearn KFold 包み／`create_cv_splitter(config)` 工場／`runner.py` の oof ゼロ埋め黙認（oof_mask で修正）／`ExperimentRunner`（実験の編成は work/ の train.py が担う。src に編成層を作ると二重実装の温床）／manifest 無し ModelRepository。

## E. 着手順：歩く骨組み（walking skeleton）を先に1本通す

**結論：歩く骨組み案を採る。** 根拠：(1) 主眼が「E2E・統合の欠落」なのだから、最大の不確実性＝結線（store の split 再書き込み拒否と `--test` 再実行の衝突、OOF 表のスキーマ設計、tmp root の扱い）を最初に潰すべきで、これらは端まで通して初めて見つかる。(2) 骨組みが通った後の各タスクは「常に緑の e2e を保ったままの差し替え」になり、退行がその場で見える。(3) この骨組みには捨てる仮実装がほぼ無い：Fake は基準トレーナーとしてテスト資産に残り、素通し特徴量は baseline 変種としてそのまま本採用になる。純粋な bottom-up は統合の失敗を最後（E-0001）まで温存する——現状の問題（単体だけある）の再生産になる。

タスク列への割付（ID は既存のまま・順序だけ変える）：

0. **T-0017 検証の仕組み**（骨組みの前に置く土台）：`checks.toml` の各段階 pytest を marker 選択（fast=unit / standard=integration / full=e2e、いずれも `not slow`）にし、既存テスト8ファイルにピラミッドの目印を付け、conftest に「未マークのテストは失敗」ガードを置く。ML モジュールに依存しない純粋な仕組みなので先に入れる。
1. **T-0014 cv.py**（骨組みの背骨）：make_folds／fold_indices／holdout_indices／run_cv＋CVResult。tests に FakeTrainer。統合テスト＝結線・fold 表の store 往復。※ stratify は最初から入れる（後付けだと fold 表スキーマが揺れる）。
2. **T-0015 train.py**：Trainer Protocol＋FoldOutcome＋SklearnTrainer。ここで sklearn を ds extra に追加。再現性・target_transform の統合テスト。
3. **T-0016（前半）models.py**：`Serializer` Protocol＋`PickleSerializer`／`ModelRecord`（版・依存記録込み）／`save_model`（版採番・原子書き・manifest・版単位の上書き拒否・pipeline 同梱）／`load_model`（指紋 fail・形式 fail・critical warn）。骨組みの「登録」を仮置きにしない最小。
4. **E-0001（骨組み）**：フォルダ・SPEC・config.yaml・code/train.py を作り、**baseline 変種だけ**で `--test` を端から端まで通す。`tests/test_e2e_experiment.py::test_e0001_smoke` を追加＝この瞬間から verify に e2e が載る。item は in-progress のまま。
5. **T-0013 features.py**：FeatureBlock／FeaturePipeline／3ブロック／漏れ検知の統合テスト。train.py の特徴量部を素書きからパイプラインに差し替え（e2e 緑のまま）。
6. **T-0012 eval 閾値選択**：select_threshold_*。train.py に「OOF で閾値を選んで results に記録」を接続。
7. **T-0016（後半）**：`ModelRegistry` Protocol＋`FileRegistry`（list/latest/get）・`list_models`＋CLI `uv run data models`・`promote_model`＋昇格記録＋champion 表示。
8. **E-0001（完了）**：interaction 変種・本規模実行（slow）・results/ 確定・SPEC の判定に従い結論を記録して done。仮説が棄却（合成データは線形なので交互作用は効かない見込み）でも done——「負の結果も記録で完了」の実地確認まで含めて完了条件。

各ステップは「スタブ＋赤テスト→実装→verify 緑」の1タスク内完結（EP-06 の進め方）を維持。4 以降は常に e2e が守っている。

## F. 残したツマミ＝既定値＋上書き条件（いま返事が要る項目はゼロ）

**読み方**：以下は「未決の質問」ではない。設計にツマミ（後で変えられる箇所）を残した所で、**すべて既定値を決めてある**。実際に案件で使う時に、その案件の事情が既定と違えば config かフラグ1つで上書きする。列挙は透明性のためで、いま答えは要らない。

- **閾値・昇格指標の値**（`thresholds:` / `promote_model(primary=…)`）→ 既定は E-0001 の例（roc_auc 0.80）。**上書き条件**：案件ごとに「成功の定義」（誤検知と見逃しのコスト比）が決まった時、config の値を変える。コードは触らない。
- **版不一致時の load（warn/fail）**→ 既定 `warn`（読める可能性を試す）。**上書き条件**：監査・規制で「版が違うモデルは読ませない」が要る案件だけ `on_dependency_mismatch="fail"`。完全性・形式の不一致は既定で常に fail（ここは選べない）。
- **再学習の材料をどこまで実体複製するか**→ 既定は指紋参照のみ（学習表は store 側に在る）。**上書き条件**：監査で「元データが消えても再現必須」の案件だけ版ディレクトリへ複製する。
- **slow を回す場所**（夜間 CI / 実験完了時に手動）→ 既定は決めない。仕組み（門番から外せる）はどちらでも受ける。**決める時期**：本規模実行が重くなって分離が要る時。
- **backend 切替（S3/DWH）の時期**→ 既定はローカル（`file:`）のまま・口だけ開ける。**決める時期**：共有が要る（チーム参加・データ量）時。

### 参考：確定済みの方針（2026-07-03）

1. **合否の閾値の値**（config.yaml `thresholds:`）→ **決着：ここで値を決めない。案件ごとのパラメータ**。設計は値を埋めず config で外から受け `passes(metrics, thresholds)` で判定する（決められる設計を担保）。E-0001 の 0.80 は「合成データ構成上まず割らない下限」の仮置きにすぎない。
2. **モデルの保存形式**→ **決着：pickle は「格下げした既定フォールバック」。直列化は注入する `Serializer` に委譲**（B-5 改訂で確定）。参考リポ2本の実務（本体は native/ONNX・pickle は限定・依存版を記録・レジストリは (model,version) キー・登録＝関門）を翻訳。核 models.py は形式非依存の封筒（manifest・指紋・版・台帳・昇格関門）だけを持ち sklearn/onnx を非 import。pickle の脆さは「依存版の記録＋load 時の critical 照合（既定 warn・完全性/形式は常に fail）＋自己記述な manifest＋指紋照合」で参考リポの「記録のみ」より一段安全にする。可搬形式（ONNX 等）は Serializer 実装を足すだけ。**残る業務判断**は次の2-a・2-b：
   - 2-a. **版不一致時の既定を warn のままにするか**（監査・規制のある案件では fail 既定＝`on_dependency_mismatch="fail"` や verify 組み込みが要り得る。引数1つで切替）。
   - 2-b. **「再学習の材料」をどこまで実体で複製するか**（既定は指紋参照のみ＝学習表は store 側に在る。参考リポ B のように分割データまで版ディレクトリへ複製するかは保持コストと監査要件の判断）。
   - 2-c. **昇格の主要指標・方向・絶対閾値**（`promote_model(primary=…, thresholds=…)`。1 と同じくパラメータで、値は案件の価値判断）。
3. **slow（本規模実行）の扱い**→ **決着：仕組み（段階×目印・門番から slow を外せる構造）は今作り込む**（C「検証の仕組み」・T-0017）。業務判断として残るのは「slow を実際に回す先＝夜間 CI で自動 か 実験を done にする時に手動か」の1点だけで、これは E-0001 まで保留でよい（仕組みはどちらでも受けられる）。
4. **backend 切替（S3/DWH）の着手時期**→ **決着：まだ着手しない。ローカルのまま**。ただし models.py も store.py と同じく config URI 解決・`file:` 以外は NotImplementedError で書き、口だけ開けておく（見越して設計・実装はしない）。着手時期は共有が要る時点（チーム参加・データ量）で判断。
