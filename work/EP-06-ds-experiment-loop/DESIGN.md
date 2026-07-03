<!-- EP-06（実験ループ）の詳細設計。全体像→各モジュール→テスト戦略→着手順。
     移植元：draft/reference/ml-competition-template-main（MIT）。裏取り済み。
     この文書は正本。着手順は item.md と一致させること。 -->
# 段階1（EP-06）実験ループ設計書 — 特徴量→学習→評価→記録→登録

## A. 全体像

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

### B-1. eval.py への追記（T-0012 閾値選択）— sklearn 不使用・numpy のみ

参考リポ `domain/threshold.py` は sklearn.metrics（f1_score / roc_curve / precision_recall_curve）に依存し、閾値候補を `linspace(0.01, 0.99, 100)` の格子で探す。移植では **候補＝y_score の一意な値の集合** に変える。格子より正確で、テストの期待値が入力の構成から厳密に導出できる（合否数値が決め打ちできる）。

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
- 実装は「score 降順に並べ、累積和で TP/FP を一括計算」（既存 roc_auc と同じ流儀の numpy ベクトル計算）。

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
- `StandardScaleBlock(columns: Sequence[str])` … fit で平均・標準偏差を学習（有状態。漏れ検知テストの被験体でもある）

blocks サブパッケージは作らない（EP-06 の「やらないこと」どおり、実験駆動で features.py に足し、増えたら分割）。

### B-3. cv.py（T-0014）— fold 表・添字対・run_cv

参考リポとの差分：`CVSplitter` は sklearn KFold の包み＋`random_state=42` の隠れ既定。非採用。fold 割当を**データ（split 層テーブル）**にし、分割の再現をコードでなくデータで担保する（核2）。`create_cv_splitter(config)` のような設定→部品の工場も作らない（実験スクリプトが組み立てる。段階1に分岐は2種しかない）。

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

### B-4. train.py（T-0015）— Trainer Protocol＋SklearnTrainer

参考リポとの差分：`train_fold` に seed が無く、乱数はモデルパラメータ任せ（暗黙）。**seed を train の明示引数**にする（核3）。また target_transform（T-0011 の成果）をここで結線する。

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

### B-5. models.py（T-0016）— 保存・読込・台帳（`harness/ds/models.py`）

`harness/models.py`（PM の Item 型）と同名だがパッケージが違う。import は `from harness.ds import models as model_store` の別名を実験雛形の規約にして混同を防ぐ。参考リポ `model_repository.py` は「ロジック無し IO」＝manifest 無し・上書き無警告・由来不明。ここを store.py と同じ規律（指紋・manifest・拒否）で強化する。

```python
@dataclass(frozen=True)
class ModelRecord:
    name: str
    work: str                         # 作業単位ID（E-0001 等）
    path: Path
    fingerprint: str                  # pickle ファイルの sha256
    data_fingerprint: str | None      # 学習に使った表の指紋（store.save の返り値と結ぶ）
    metrics: dict[str, float]
    config: dict[str, object]         # 変種名・seed・n_folds 等
    created: str                      # ISO 8601

def save_model(
    root: Path, model: object, *, name: str, work: str,
    data_fingerprint: str | None = None,
    config: Mapping[str, object] | None = None,
    metrics: Mapping[str, float] | None = None,
) -> ModelRecord:
    """pickle＋manifest.yaml を書く。既存の同名は拒否（上書きしない。別名にするか消してから）。
    置き場は config の data backend から解決：<uri>/work/<work>/models/<name>.pkl（store と同じ規約）。"""

def load_model(root: Path, *, name: str, work: str) -> tuple[object, ModelRecord]:
    """manifest が無い pickle は読まない。pickle の指紋が manifest と食い違っても読まない。"""

def list_models(root: Path, *, work: str | None = None) -> list[ModelRecord]:
    """manifest を走査した台帳ビュー。CLI `uv run data models` から表示（status 本体はいじらない）。"""
```

- 一時ファイル→rename の原子的書き込み、`file:` 以外の URI は NotImplementedError、は store.py と同じ実装パターンを踏襲（backend 差し替え可能性を保つ）。
- pickle は「自分が書いたローカルファイルだけ読む」前提を docstring に明記（manifest 指紋照合がその機械的裏付け）。

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

### e2e→verify の接続

1. **接続点は pytest の e2e テストであって checks.toml の新コマンドではない**。checks.toml の `[full] pytest -q` はマーカー無指定＝全部実行なので、`tests/test_e2e_experiment.py` を追加した時点で `uv run verify` に e2e スモークが自動的に載る。checks.toml は変更不要（入口を増やさない）。
2. e2e テストは実験スクリプト**そのもの**を subprocess で叩く（`sys.executable` ＋ `--test --root <tmp>`）。これにより「雛形から乖離した実験スクリプト」「テストだけ通る二重実装」が構造的に不可能になる——verify が落ちるのはスクリプト本体が壊れたとき。
3. E-0001 の `verified_by: tests/test_e2e_experiment.py::test_e0001_smoke` とし、既存の pm.lint（`::名` の実在検査・done 実験の results/ 必須）にそのまま噛み合わせる。
4. 重い方は `slow` マーカーで分離。当面 full は全実行のまま（LogisticRegression×n=2000 は数秒で予算内）。**full の所要が2分を超えたら** checks.toml の full を `pytest -q -m "not slow"` に変え、slow は CI の夜間または実験完了時の手動実行に移す——この切替条件を数値で決めておく。
5. 追加の機械的ガード：pm.spec_lint に「`work/**/code/*.py` に `np.random.seed` / `random.seed` を含んだら error」を1項目足す。グローバル種の禁止をレビュー頼みにしない。

## D. 横断的な設計判断

**D-1. sklearn は ds extra に追加する。ただし src の核は import しない（結論）。**
- pyproject の `[project.optional-dependencies] ds` に `scikit-learn>=1.6` を追加。mypy overrides に `sklearn.*` の ignore_missing_imports を追加。
- 理由：(1) E-0001 には本物の学習器が要る。ロジスティック回帰の自前実装は本題（実験ループの結線）の外で、保守負債にしかならない。(2) eval の AUC・閾値選択・make_folds を自前 numpy に保つのは、既に半分できており（roc_auc 自前）、決定性・依存の軽さ・テスト期待値の導出可能性で勝る。(3) 分水嶺は「**src/harness/ds/ のどのファイルも sklearn を import しない**」に引く。sklearn が現れるのは実験コード（model_factory の中身）とテストだけ。核の型検査・単体テストは sklearn 無しの環境でも通る。LightGBM も同じ扱いで足せる。

**D-2. numpy/polars の境界は1点。** polars＝表とメタデータの世界（store/schema/fold表/FeatureBlock）、numpy＝学習の数値の世界（X, y, oof, 指標, 変換）。変換は `FeaturePipeline` の出力 DataFrame を `.to_numpy()` する1か所だけ。列順は `feature_names()` で記録し、モデル manifest の config に残す（推論時の列ずれ検知の材料）。

**D-3. fold ごとの種は SeedSequence で導出。** `run_cv` は受け取った seed から `np.random.SeedSequence(seed).spawn(k)` で fold 別の種を作り、`trainer.train(..., seed=fold_seed)` に渡す。呼ぶ場所で決めた種だけが効く、という AGENTS の規約と一致。

**D-4. 特徴量の fit は「学習に使う行」でだけ行う。** 段階1の run_cv は行列 X を受け取る設計（計画どおり）で、特徴量は CV の前に作る。これが漏れなしで成り立つのは段階1のブロックが無状態（Columns/Interaction）または固定分割の train でだけ fit する使い方だから。**fold 内 fit が必要な有状態ブロック（target encoding 等）を導入する時が `run_cv_with_features(...)` を足す時**——この境界条件を features.py の docstring に明記し、先回りの複雑化はしない。

**D-5. mypy の範囲は src・tests のまま。** work/ の実験コードは変更が激しく、型検査は ruff（`.` 全体）＋e2e スモークで担保する。実験コードが src に昇格する時に strict の対象になる。

**D-6. 参考リポで非採用を確認したもの（裏取り済み）：** `features/base.py set_seed`（グローバル種）／`cv.py` の `random_state=42` 隠れ既定と sklearn KFold 包み／`create_cv_splitter(config)` 工場／`runner.py` の oof ゼロ埋め黙認（oof_mask で修正）／`ExperimentRunner`（実験の編成は work/ の train.py が担う。src に編成層を作ると二重実装の温床）／manifest 無し ModelRepository。

## E. 着手順：歩く骨組み（walking skeleton）を先に1本通す

**結論：歩く骨組み案を採る。** 根拠：(1) 主眼が「E2E・統合の欠落」なのだから、最大の不確実性＝結線（store の split 再書き込み拒否と `--test` 再実行の衝突、OOF 表のスキーマ設計、tmp root の扱い）を最初に潰すべきで、これらは端まで通して初めて見つかる。(2) 骨組みが通った後の各タスクは「常に緑の e2e を保ったままの差し替え」になり、退行がその場で見える。(3) この骨組みには捨てる仮実装がほぼ無い：Fake は基準トレーナーとしてテスト資産に残り、素通し特徴量は baseline 変種としてそのまま本採用になる。純粋な bottom-up は統合の失敗を最後（E-0001）まで温存する——現状の問題（単体だけある）の再生産になる。

タスク列への割付（ID は既存のまま・順序だけ変える）：

1. **T-0014 cv.py**（骨組みの背骨）：make_folds／fold_indices／holdout_indices／run_cv＋CVResult。tests に FakeTrainer。統合テスト＝結線・fold 表の store 往復。※ stratify は最初から入れる（後付けだと fold 表スキーマが揺れる）。
2. **T-0015 train.py**：Trainer Protocol＋FoldOutcome＋SklearnTrainer。ここで sklearn を ds extra に追加。再現性・target_transform の統合テスト。
3. **T-0016（前半）models.py**：save_model／load_model と manifest・上書き拒否だけ（list_models・CLI 表示は後半へ）。
4. **E-0001（骨組み）**：フォルダ・SPEC・config.yaml・code/train.py を作り、**baseline 変種だけ**で `--test` を端から端まで通す。`tests/test_e2e_experiment.py::test_e0001_smoke` を追加＝この瞬間から verify に e2e が載る。item は in-progress のまま。
5. **T-0013 features.py**：FeatureBlock／FeaturePipeline／3ブロック／漏れ検知の統合テスト。train.py の特徴量部を素書きからパイプラインに差し替え（e2e 緑のまま）。
6. **T-0012 eval 閾値選択**：select_threshold_*。train.py に「OOF で閾値を選んで results に記録」を接続。
7. **T-0016（後半）**：list_models 台帳・`uv run data models`・load 時の指紋照合。
8. **E-0001（完了）**：interaction 変種・本規模実行（slow）・results/ 確定・SPEC の判定に従い結論を記録して done。仮説が棄却（合成データは線形なので交互作用は効かない見込み）でも done——「負の結果も記録で完了」の実地確認まで含めて完了条件。

各ステップは「スタブ＋赤テスト→実装→verify 緑」の1タスク内完結（EP-06 の進め方）を維持。4 以降は常に e2e が守っている。

## F. 人の判断待ち（業務価値に関わる決定のみ）

1. **合否の閾値の値**（E-0001 config.yaml の `thresholds:`）。roc_auc 0.80 は「データ構成上まず割らない下限」としての仮置き。実案件でこのテンプレートを使うとき、何をもって「実験成功」とするかは業務目標（誤検知と見逃しのコスト比）の決定事項。
2. **モデルの保存形式と引き渡し先**。pickle＋manifest はローカル・同一 Python 環境内では十分だが、他システム・他言語への引き渡し（ONNX 等の可搬形式）が要るかは案件の運用要件次第。要るなら T-0016 のインターフェースに export 口を足す。
3. **slow（本規模実行）を CI で回すか**。現状はローカル verify で数秒だが、実データ・重いモデルに移った時に「CI の計算時間・費用をどこまで払うか」は予算判断。切替条件（full 2分超）は C で決めてある。
4. **backend 切替（S3/DWH）の着手時期**。インターフェースは file: 前提で固定済みだが、共有が必要になる時点（チーム参加・データ量）は業務側のマイルストーン次第。
