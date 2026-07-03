<!-- EDA・評価部品の詳細設計（2026-07-03・Fable）。
     対象リポ：C:\Users\hj7745\Desktop\mlops\harness-template
     移植元（裏取り済み・MIT）：draft/reference/ml-competition-template-main の eda/・evaluation/・domain/。
     形式は work/EP-06-ds-experiment-loop/DESIGN.md の R 節に倣う。実装はしない（設計のみ）。
     改訂1（2026-07-03）：利用者指摘「EDA の結果は人も見る」を受け、判断1 を
     「marimo を薄いビューとして導入（正本は YAML のまま）」へ変更。§0・§2・§3・§4・§5・§6・§7・§8 を更新。
     改訂2（2026-07-03）：完全性スイープ。業界標準の EDA・エラー分析と参考リポ全体（profiler/categorical/
     threshold/error_analysis）を再点検し、足りない汎用パーツを §9 に追加。§5 の着手順に織り込み
     （T-0029・T-0030 を新設）。既存の設計・実装（T-0024/T-0025）は延長のみ・壊さない。 -->

# EDA・評価部品の詳細設計 — 構造化レポート・分布差検出・指標レジストリ・エラー分析・重要度

> 前提の憲法：DEC-0006（標準を再発明しない）・DEC-0007（背骨は sklearn Pipeline・clone-per-fold）・
> DEC-0008（作る/使うの基準＝sklearn が十分か）・DEC-0009（部品は入口まで作って完了）・
> method.md（歩く骨組み優先・Rule of Three・スキルは一覧へ導くだけ）。

## 0. 全体像

追加は `src/harness/ds/` に **2 ファイル新設＋1 ファイル延長**（平ら構成を維持。9→11 ファイル。
サブパッケージ化の発火条件「10 個/500 行」は features.py のブロック数の条件であり、ds/ のファイル数の上限ではない）
＋**リポ直下に marimo 雛形 1 本**（notebooks/eda.py。人向けの薄いビュー・数値ロジック無し）。

```
src/harness/ds/
├── eda.py        【新設】テーブルの構造化レポート（profile）・目的変数の要約・相関・
│                        train/test 比較（統計量・カテゴリ・PSI）・分布差 AUC（run_cv の合成）
├── analysis.py   【新設】OOF 予測の深掘り：セグメント別指標・誤差の大きい行・並べ替え重要度
└── eval.py       【延長】METRICS レジストリ（分類＋回帰・向き付き）・evaluate の指標選択・
                         evaluate_regression・passes の向き対応

notebooks/
└── eda.py        【新設・雛形】marimo の薄いビュー（人向け）。上の eda/analysis の関数を呼んで
                         polars の表と図を表示するだけ（集計・指標のロジックを notebook に書かない）。
                         e2e スモークが毎回ヘッドレス実行して腐りを防ぐ（§3・§4 判断1）
```

データの流れ（既存の部品に「読む側」を足すだけ。学習系は触らない）：

```
store.load(table_id) ──→ eda.profile / target_summary / correlations   … 実験の前（調査 kind）
        └ train・test 2 表 ──→ eda.compare（統計・カテゴリ・PSI）        … 結合統計は API 上作れない
                          └──→ eda.drift_auc（build_estimator＋run_cv の合成・OOF AUC）
run_experiment → CVResult ──→ analysis.segment_metrics / worst_rows      … OOF 予測の深掘り
                          └──→ analysis.cv_permutation_importance         … fold の valid 行だけで計算
eval.METRICS ──→ evaluate / evaluate_regression / passes ──→ config の thresholds / `uv run data metrics`
```

**第一の出力（＝正本）はすべて「機械可読な構造化レポート」**（polars DataFrame / dict）。YAML に落とせて、
テストで期待値を書け、エージェントがそのまま読める。**人は同じ関数を呼ぶ marimo の薄いビュー**
（notebooks/eda.py 雛形）で表と図として見る（§4 判断1【改訂】）。図・ノートブックを正本にはしない
（レポートの数値ロジックはすべて src 側＝二重化しない）。

## 1. モジュール詳細設計（型シグネチャ）

### 1-1. eda.py — テーブルの構造化レポートと train/test 比較

先頭 docstring（要旨）：「EDA の第一の出力は構造化レポート（polars/dict）。図でなくデータで返す
（テストでき・エージェントが読める）。train/test の比較は 2 つの DataFrame を別々に受け、
結合した統計は計算しない（リーク禁止を API の形で守る）。」

```python
# --- 1 テーブルの要約 ---

@dataclass(frozen=True)
class TableProfile:
    """1 テーブルの構造化レポート。to_dict() で YAML にそのまま落ちる。"""
    n_rows: int
    n_columns: int
    columns: pl.DataFrame      # column, dtype, null_count, null_ratio, n_unique（df の列順のまま）
    numeric: pl.DataFrame      # column, mean, std, min, q25, median, q75, max（数値列のみ）
    categorical: pl.DataFrame  # column, n_unique, top_value, top_count, top_ratio（String か n_unique<=max_categories）
    duplicate_rows: int        # 全列一致の重複行数
    def to_dict(self) -> dict[str, object]: ...  # polars は行の list[dict] へ。キー順固定（決定的な出力）

def profile(df: pl.DataFrame, *, max_categories: int = 50) -> TableProfile:
    """テーブルの基本レポート。集計は polars（describe/null_count/n_unique）に委譲し、束ねるだけ。"""

def target_summary(
    df: pl.DataFrame, *, target: str, task: Literal["classification", "regression"] = "classification"
) -> dict[str, object]:
    """目的変数の要約。分類＝クラス別の件数と比率（不均衡度）。回帰＝統計量（mean/std/min/q25/median/q75/max）。
    「目的変数を確認せずに学習へ進まない」（参考リポの禁止事項）の機械的な入り口。"""

def correlations(df: pl.DataFrame, *, target: str, columns: Sequence[str] | None = None) -> pl.DataFrame:
    """数値列と目的変数の相関（np.corrcoef）。列 = feature, correlation。|r| 降順。
    定数列（分散 0）は 0.0（NaN を黙って混ぜない）。"""

def high_correlation_pairs(
    df: pl.DataFrame, *, threshold: float = 0.99, columns: Sequence[str] | None = None
) -> pl.DataFrame:
    """相関の高い列ペア（列 = a, b, correlation）。既定 0.99 はリーク疑い検出（参考リポ Phase4）。
    0.8 に下げれば多重共線性の点検にも使える（引数で外から）。相関行列は np.corrcoef を 1 回呼ぶだけ。"""

# --- train/test 比較（リーク禁止を構造で） ---

@dataclass(frozen=True)
class CompareReport:
    """train/test 比較の構造化レポート。統計は各側で別々に計算済み（結合統計は存在しない）。"""
    n_train: int
    n_test: int
    numeric: pl.DataFrame     # column, train_mean, test_mean, train_std, test_std,
                              #        mean_gap(=|train_mean-test_mean|/train_std・train_std=0 は null), psi
    categorical: pl.DataFrame # column, n_train_only, n_test_only, train_only_top, test_only_top（上位数件の list）,
                              #        test_coverage(= train に在るカテゴリで覆われる test 行の割合), psi
    def to_dict(self) -> dict[str, object]: ...

def compare(
    train: pl.DataFrame, test: pl.DataFrame, *,
    columns: Sequence[str] | None = None, max_categories: int = 50, psi_bins: int = 10,
) -> CompareReport:
    """train/test の列ごとの分布比較。参考リポ Phase5 の 5-1〜5-3 を 1 関数に畳む。
    リーク禁止は API の形で守る：2 つの DataFrame を受け、各側で独立に集計する。
    結合してから集計する経路はこのモジュールに存在しない。"""

def psi(train: pl.Series, test: pl.Series, *, bins: int = 10) -> float:
    """PSI（母集団安定性指標）。数値列＝ビン境界を train の分位点だけから作る（test を見ない＝リーク無し）。
    カテゴリ列＝train に現れたカテゴリ＋「その他」1 束。空ビンは小さい床値（1e-6）で 0 割を防ぐ。
    目安：0.1 未満=安定・0.1〜0.25=要注意・0.25 以上=大きな変化（docstring に記載・門番にはしない）。"""

# --- 分布差 AUC（adversarial validation。既存部品の合成） ---

@dataclass(frozen=True)
class DriftResult:
    """train/test を見分ける分類器の成績。auc=0.5 は見分けられない（分布が近い）。"""
    auc: float                 # OOF の AUC
    fold_aucs: list[float]
    n_train: int
    n_test: int
    estimators: list[object]   # fold 別の学習済み Pipeline（どの列が効くかは analysis.permutation_importance へ）

def drift_auc(
    train: pl.DataFrame, test: pl.DataFrame, *,
    columns: Sequence[str], seed: int, n_folds: int = 5,
    spec: Mapping[str, Any] | None = None,     # build_estimator の spec。省略時は columns 素通し
    model: Mapping[str, Any] | None = None,    # build_model の spec。省略時は {kind: logreg}
) -> DriftResult:
    """train/test を見分ける分類器を交差検証し OOF AUC を返す。
    実装は既存部品の合成だけ：特徴量列だけを縦に結合し、所属（train=0/test=1）を y にして
    build_estimator → make_folds(stratify_by=所属) → run_cv。目的変数は一切使わない（リーク無し）。
    LightGBM は不要（モデルは config と同じ spec で選べる＝MODELS が増えれば自動で選択肢が増える）。
    AUC が高い（目安 0.7 以上）ときは、効いている列を analysis.cv_permutation_importance で特定して原因を調べる。"""
```

参考リポとの差分（裏取り）：AdversarialValidator（LightGBM 直書き・クラス・print 進捗）は取り込まず、
`run_cv`＋`build_estimator` の合成 1 関数にする。feature_importance の同梱もしない
（重要度は analysis の並べ替え重要度を合成＝二重実装を作らない）。

### 1-2. eval.py 延長 — METRICS レジストリ（分類＋回帰・向き付き）

**レジストリにする（単純な関数群に留めない）と判断**。根拠：
(1) 指標名は既に config の語彙（`thresholds: {roc_auc: 0.80}`）＝「config で選べる種」であり、DEC-0009 の
機械可読カタログの対象。(2) 回帰指標（rmse/log_loss は小さいほど良い）が入ると `passes` の `>=` 決め打ちが
壊れる——**向き（higher_is_better）は指標の属性**で、レジストリに置くのが唯一の一貫した置き場。
(3) BLOCKS/ENCODERS/MODELS と同型になり、`uv run data metrics` と test_catalog（説明文必須）に同じ作法で載る。

```python
@dataclass(frozen=True)
class Metric:
    """指標 1 つの登録情報。fn は sklearn.metrics の薄い包み（再発明しない）。"""
    fn: Callable[[NDArray[np.float64], NDArray[np.float64]], float]
    task: Literal["classification", "regression"]
    input: Literal["score", "label", "value"]  # score=確率・label=閾値後のラベル・value=回帰の予測値
    higher_is_better: bool
    description: str                            # 一覧コマンドに載る 1 行（test_catalog で必須検査）

# 既存の accuracy / roc_auc はそのまま残し登録する（互換維持）。新規は sklearn 素通しの薄い関数：
#   分類（score）: roc_auc / pr_auc(=average_precision_score) / log_loss（↓）
#   分類（label）: accuracy / f1 / precision / recall（zero_division=0）
#   回帰（value）: rmse(=root_mean_squared_error) / mae / mape(=mean_absolute_percentage_error・sklearn の比率のまま。×100 しない)
METRICS: dict[str, Metric] = {...}  # 足したら 1 行（他レジストリと同じ）

def evaluate(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *,
    threshold: float = 0.5, metrics: Sequence[str] | None = None,
) -> dict[str, float]:
    """分類の指標をまとめて返す。既定は分類の全登録指標（label 系は threshold でラベル化してから）。
    metrics=["roc_auc", ...] で選べる（回帰指標の名を渡すと ValueError）。"""

def evaluate_regression(
    y_true: NDArray[np.float64], y_pred: NDArray[np.float64], *, metrics: Sequence[str] | None = None
) -> dict[str, float]:
    """回帰の指標をまとめて返す。既定は回帰の全登録指標。"""

def metric_fn_for(
    task: Literal["classification", "regression"], *, threshold: float = 0.5, metrics: Sequence[str] | None = None
) -> MetricFn:
    """run_cv / run_experiment の metric_fn に渡す形へ束ねる（task の分岐はここ 1 か所）。"""

def passes(metrics: dict[str, float], thresholds: dict[str, float]) -> bool:
    """【改訂】向きをレジストリで解決する：higher_is_better なら >=、そうでなければ <=（例 log_loss: 0.5 は
    「0.5 以下で合格」）。thresholds に METRICS 未登録の名があれば ValueError（typo を黙って不合格にしない）。
    metrics 側に無い登録済みの名は従来どおり不合格。"""
```

**縁の吸収**（DEC-0006「標準が例外を投げる縁だけ方針で吸収」・roc_auc の 0.5 と同じ流儀）：
- `log_loss` は `labels=[0, 1]` を渡す（単一クラスの fold で落ちない）。
- `pr_auc` は y_true が単一クラスなら定義できない → 陽性なし 0.0・陽性のみ 1.0 を返す（docstring に明記）。

**タスク種の置き場**：実験 config に `task: classification | regression`（省略時 classification）を追加。
`run_experiment(..., task=...)` が `predict=("proba"|"value")` と `metric_fn_for(task)` を配線する
（run_cv・CVResult は無変更。既存 E-0001 は config 無変更で従来どおり動く）。
回帰経路を死蔵にしないため、`MODELS` に `ridge`（sklearn.linear_model.Ridge・random_state 配線）を 1 行足し、
回帰の統合テストで端まで通す（§6・§5 手順 8。工場 1 つ＝DEC-0006 の想定どおりの追加口）。

**互換への影響（明示）**：`evaluate` の既定の返り値キーが {accuracy, roc_auc} から分類の全登録指標に増える
（追加のみ・既存キーは不変）。fold_metrics・results/metrics.yaml に列が増える。既存テストで dict の完全一致を
見ている箇所は「部分集合の確認」へ直す（数値の期待値は不変）。

### 1-3. analysis.py — OOF 予測の深掘り（セグメント・誤差・重要度）

先頭 docstring（要旨）：「すべて OOF/valid の予測で呼ぶ（train の予測で呼ぶと過大評価・test のラベルは使わない）。
入口（cv_permutation_importance）は fold の valid 行だけを使う形にしてこの規律を構造で守る。」

```python
def segment_metrics(
    segments: pl.Series, y_true: NDArray[np.int_], y_score: NDArray[np.float64], *,
    task: Literal["classification", "regression"] = "classification",
    threshold: float = 0.5, metrics: Sequence[str] | None = None,
) -> pl.DataFrame:
    """セグメント（カテゴリ列）別の指標表。列 = segment, count, <指標...>。count 降順。
    指標の計算は eval の evaluate / evaluate_regression に委譲（polars group_by で回すだけ）。
    OOF 予測（cv.oof[oof_mask]）で呼ぶこと。連続値で切りたいときは事前に列をビン化して渡す
    （polars の qcut 1 式。ビン化専用関数は作らない）。"""

def worst_rows(
    df: pl.DataFrame, y_true: NDArray[np.int_], y_score: NDArray[np.float64], *,
    n: int = 20, task: Literal["classification", "regression"] = "classification",
) -> pl.DataFrame:
    """誤差の大きい行の一覧（df の列＋ y_true, y_score, error）。error 降順の上位 n 行。
    error は分類＝|y_true − y_score|（確率との差）・回帰＝|y_true − y_pred|。
    「どんな行で外しているか」をエージェントが特徴量追加の仮説にする入り口。"""

def permutation_importance(
    estimator: object, x: pl.DataFrame, y: NDArray[np.float64], *,
    metric: str, seed: int, n_repeats: int = 5, columns: Sequence[str] | None = None,
    predict: Literal["proba", "value"] = "proba",
) -> pl.DataFrame:
    """入力列の並べ替え重要度。列 = column, importance_mean, importance_std。importance = 悪化量
    （METRICS の向きで符号を揃える＝常に「大きいほど効いている」）。
    estimator は学習済みの Pipeline 丸ごと（モデル非依存・LightGBM が来ても無変更）。
    x は fit に使っていない行（fold の valid / holdout）で呼ぶこと。
    sklearn.inspection.permutation_importance を使わない理由（DEC-0008 の判定）：sklearn 版は
    numpy/pandas 入力が前提で、polars 入力（特に MultiHot の list 列）の Pipeline に入らない。
    numpy 往復の変換器を挟む案は list 列・混在 dtype で壊れる。よって「隙間」——並べ替えの繰り返し
    （約 30 行）だけ自作し、指標の計算は METRICS（sklearn.metrics）へ委譲する。"""

def cv_permutation_importance(
    cv: CVResult, x: pl.DataFrame, y: NDArray[np.float64], splits: Splits, *,
    metric: str, seed: int, n_repeats: int = 5, columns: Sequence[str] | None = None,
    predict: Literal["proba", "value"] = "proba",
) -> pl.DataFrame:
    """CV 全体の並べ替え重要度（推奨の入口）。fold k の estimator を「その fold の valid 行」だけで
    評価して平均する——「OOF なしに重要度を解釈しない」（参考リポの禁止事項）を引数の形で守る。
    drift_auc の結果にも使える（DriftResult.estimators＋同じ splits を渡す＝分布差の原因列の特定）。"""
```

参考リポとの差分：ErrorAnalyzer クラス（状態持ち）→ 純関数 2 つに畳む（状態を持つ理由が無い）。
自前のスコア関数辞書（mape/mae/mse 手書き）→ METRICS（sklearn）へ委譲。normalize・累積重要度・
削除候補抽出などの派生 API → 作らない（DataFrame を返せばエージェントが polars で加工できる）。

## 2. 入口（DEC-0009：この設計の完了条件に含む）

| 部品 | ①機械可読カタログ | ②docstring | ③CLI | ④スキル/雛形の導線 |
|---|---|---|---|---|
| METRICS（指標） | METRICS レジストリ（説明文必須を test_catalog に追加） | 各 Metric.description＋evaluate 系 | **`uv run data metrics`**（name/task/向き/説明の一覧） | experiment スキル「合否と指標」節・config の thresholds コメント |
| eda.profile ほか要約 | —（config の種ではない＝カタログ対象外。入口は CLI＋スキル） | 関数 docstring に「何を返すか・YAML への落とし方」 | **`uv run data profile <table_id> [--target 列 --task 種]`**（TableProfile＋target_summary を YAML で標準出力） | **eda スキル（新設）** |
| eda.compare / psi | — | 同上＋リーク禁止の明記 | **`uv run data compare <train_id> <test_id> [--auc --seed N]`**（CompareReport を YAML 出力・--auc で drift_auc も） | eda スキル |
| eda.drift_auc | モデル・特徴量は既存 MODELS/BLOCKS の spec を流用（カタログ済み） | docstring に目安 0.7 と次の一手 | `data compare --auc`（既定 logreg・5fold） | eda スキル |
| eda ノートブック（人のビュー・marimo） | —（正本は上の YAML。ビューはカタログの対象外） | 雛形冒頭の md セルに「同じ関数を呼ぶだけ・ロジックと結論を書かない」規律 | —（CLI 化しない。`uv run marimo edit/run` で開く） | **notebooks/eda.py 雛形（新設・入口④）**＋eda スキル手順 (5) |
| analysis 3 関数 | — | docstring に「OOF で呼ぶ」規律 | —（予測データが要るため CLI 化しない。実験フォルダから呼ぶ） | experiment スキル「結果の深掘り」節（新設） |
| task: regression 経路 | MODELS に `ridge` 1 行（既存カタログに自動で載る） | 工場 docstring | 既存 `uv run data models` に載る | experiment スキルの config 説明に `task:` を 1 行 |

**CLI の流儀**は既存 cli.py（typer・data_app）どおり：サブコマンドを `@data_app.command` で足し、
出力は決定的（キー順固定の YAML）。`data profile` / `data compare` は store.load 経由（=検証済みテーブルだけを
見る。生 CSV を直接読む口は作らない——データは store を通って入る、という既存の規律のまま）。

**スキルの構成**：
- **eda スキル（新設）**——method.md E 節が予告済み（「eda は最初の調査 kind の実験と同じタスクで作る」）。
  20 行前後・手順：(1) 調査は kind: investigation の作業単位を作る（結論を results/ に YAML で残す）
  (2) `uv run data list` → `data profile <id>`（--target で目的変数の要約） (3) train/test があれば
  `data compare`（PSI・カテゴリ差）→ 差が疑わしければ `--auc` (4) auc が目安 0.7 以上なら
  cv_permutation_importance で原因列を特定し、除外/変換の仮説を experiment スキルへ渡す
  (5) **人が見る・見せるとき**は notebooks/eda.py を調査フォルダへコピーし、`uv run marimo edit <コピー>`
  （対話探索）または `uv run marimo run <コピー>`（閲覧）。ビューは harness.ds の**同じ関数**を呼ぶだけ——
  集計・指標のロジックや結論を notebook に書かない（結論は従来どおり results/ の YAML）。
  してはいけないこと：train/test を結合して統計を計算しない・目的変数を確認せず学習に進まない・
  図・notebook をレポートの正本にしない（正本は YAML。図は marimo 内の表示か results/ 置きの副産物）。
- **evaluation スキルは新設しない**——method.md E 節の既決（「参考リポの evaluation は experiment に畳める。
  スキルを増やすと発火が割れる」）に従い、**experiment スキルに「結果の深掘り」節を追加**：
  segment_metrics（どの層で外すか）→ worst_rows（どんな行で外すか）→ cv_permutation_importance
  （どの列が効くか）→ 特徴量仮説は features スキルへ。すべて OOF で。

**雛形（E-0001）との接続**：train.py は触らない（run_experiment の task 既定が classification のため無変更で動く）。
experiment スキルの手順 2 に「実データの実験は先に `data profile`／train・test があれば `data compare` を見る」を
1 行追加。回帰の実験雛形は最初の回帰実験（E-000x）を作るときに E-0001 のコピーとして生む（Rule of Three：
先回りで 2 本目の雛形を作らない。config の `task: regression`・`model: {kind: ridge}`・thresholds を
`{rmse: ...}` にするだけで train.py は共通のまま、を統合テストで先に担保しておく）。

**ノートブック雛形（notebooks/eda.py）の中身と運用**——E-0001 と同じ「実行される雛形」方式：
- **形式**：marimo の純 Python（.py）。ipynb は導入しない（diff・lint・直実行に乗らない）。
  ファイル末尾は marimo 標準の `if __name__ == "__main__": app.run()` ——つまり
  `python notebooks/eda.py` で**全セルがヘッドレス評価**され、例外はそのまま非零終了になる（e2e がこれを叩く）。
- **パラメータ**：先頭セルで環境変数 `HARNESS_EDA_TRAIN`（既定 "train"）・`HARNESS_EDA_TEST`（既定 空）を読む
  （環境変数なら `python` 直実行・`marimo edit` のどちらでも同じ口で効く）。TEST が空なら compare 系のセルは
  「test 未指定」と表示して**落ちない**（1 表だけでも雛形は端まで通る）。
- **セル構成**：store.load → profile 表・target_summary・correlations 表・数値列の分布図と相関バー
  （polars `df.plot` = altair）→（test があれば）compare 表・PSI 表・drift_auc。
  **表示する数値はすべて harness.ds.eda / analysis の返り値そのまま**（notebook 内での再集計を禁止。§3 の構造検査）。
- **置き場と命名**：雛形はリポ直下 `notebooks/eda.py` の 1 本だけ（Rule of Three：2 本目の雛形は作らない）。
  案件の探索は調査単位のフォルダへ `eda.py` としてコピー（フォルダ同居の原則どおり成果物として残す）。
  **門番（e2e スモーク）に載るのは雛形だけ**——コピーは done の results/ 必須検査側で拾う（E-0001 とコピー実験の
  関係と同型）。

## 3. テストピラミッド（期待値はデータ構成から導出・金メッキ禁止）

| 層 | 対象 | 代表テスト | 合否の根拠数値（構成から導出） | マーカー |
|---|---|---|---|---|
| unit | eda.profile | 欠損・重複・型 | 10 行の df に null を 2 個入れる → null_count==2・null_ratio==0.2 厳密。同一行を 1 組作る → duplicate_rows==1 | unit |
| unit | eda.target_summary | クラス比率 | y を 0×6・1×4 で構成 → {0: 0.6, 1: 0.4} 厳密 | unit |
| unit | eda.correlations | 相関と定数列 | x1=[1..5]・target=x1 → r==1.0。定数列 → 0.0（NaN を返さない） | unit |
| unit | eda.psi | 同一分布・境界の学習元 | train==test（同一 Series）→ psi==0.0 厳密。**test 側の値を変えてもビン境界が不変**（境界は train の分位点だけ由来＝リーク無しの構造検査） | unit |
| unit | eda.psi | 既知のずれ | カテゴリを train {a:50,b:50}・test {a:100} で構成 → PSI は定義式へ手代入した値と一致（比率が単純なので手計算できる） | unit |
| unit | eda.compare | 共通/固有カテゴリ | train={a,b,c}・test={b,c,d} と構成 → train_only={a}・test_only={d}・test_coverage は d の行数から厳密 | unit |
| unit | eval.METRICS | 登録の整合 | 全項目に description が非空・task と input の組が妥当（test_catalog へ追加＝既存 BLOCKS/ENCODERS と同型） | unit |
| unit | eval.evaluate_regression | 値の導出 | y_true=[0,0]・y_pred=[3,4] → mae==3.5・rmse==√12.5（電卓で導ける構成） | unit |
| unit | eval.passes | 向き | {"log_loss": 0.4} は閾値 {"log_loss": 0.5} で合格・0.6 なら不合格（小さいほど良い）。未登録名 → ValueError | unit |
| unit | eval 縁の吸収 | 単一クラス fold | y 全 0 で log_loss が落ちない・pr_auc==0.0（方針値・docstring と一致） | unit |
| unit | analysis.segment_metrics | 完全と全外し | セグメント A は y==pred・B は y!=pred に構成 → accuracy が A==1.0・B==0.0 厳密 | unit |
| unit | analysis.worst_rows | 並び | error を等差で構成 → 上位 n 行の id が構成どおり | unit |
| unit | notebooks/eda.py の規律 | ビューは呼ぶだけ | 雛形の source を文字列検査：`harness.ds.eda` を import している・`sklearn` を import していない（「数値ロジックをビューに書かない」の機械的近似。test_structure と同型の構造検査） | unit |
| integration | analysis.permutation_importance | 無視列の重要度 0 | estimator の features を Columns(["x1"]) だけにする → **x2 の importance==0.0 厳密**（構造上 x2 は予測に入らない）・x1 は > 0。seed 同一で再現 | integration |
| integration | eda.drift_auc | 見分く/見分けられない | (a) test = train の x1 に +10（雑音 std1 の 10σ）→ auc >= 0.95（構成上ほぼ完全分離）。(b) 特徴量が定数列 1 本 → 予測スコアが全行同値 → auc==0.5 厳密（roc_auc の同値スコア処理） | integration |
| integration | CLI | data profile / compare / metrics | conftest の Project に合成テーブルを save → subcommand 実行 → 終了コード 0・YAML が parse でき n_rows 等が構成と一致 | integration |
| integration | 回帰経路 | run_experiment(task="regression") | y = 2·x1 + 雑音(std 0.1) の合成 → ridge の OOF rmse <= 0.2（信号:雑音から導出できる上限）・passes が {rmse: 0.2} で合格 | integration |
| e2e | 既存 E-0001 | 無変更で緑のまま | evaluate のキー追加が additive であることの回帰確認（既存 e2e がそのまま門番） | e2e |
| e2e | notebooks/eda.py スモーク | 全セルがヘッドレスで通る | 合成 train/test を tmp プロジェクトの store へ save → `sys.executable notebooks/eda.py`（cwd=tmp・`HARNESS_EDA_TRAIN/TEST` で指定）を subprocess 実行 → **終了コード 0 のみ**を検査。図の画素・描画結果・HTML は比較しない（「落ちない・生成される」だけが期待値）。TEST 未指定の 1 表経路も同じ枠でもう 1 回（compare セルが落ちないこと） | e2e |

図の検査は「実行して落ちない」まで（画素・見た目の比較はしない）＝**図があってもテストは壊れない**。
数値の期待値検査はすべて src 側の関数（上の unit/integration）が持ち、notebook はその関数を呼ぶだけなので
スモークに数値期待値は不要。乱数は全関数 `seed=` 明示引数（drift_auc・permutation_importance）。
YAML 出力はキー順固定＝文字列比較でなく parse して値を確かめる。

## 4. 横断的な設計判断

**判断1.【改訂】marimo を「薄いビュー」として導入する（正本は構造化レポートのまま）。**
初版は「読者はエージェント・品質担保は機械検査」を理由に導入しない判断だったが、利用者指摘のとおり
**EDA の結果は人も見る**。初版が挙げた 3 つの懸念は「notebook を正本にする」場合のものであり、
正本を YAML に保ったままビューを重ねる形なら次のとおりすべて解ける：
- **(a) 機械検査できない → 検査対象を変えない。** 正本は従来どおり検査済みの関数（profile/compare/…）と
  その YAML（`uv run data profile/compare` → results/）。エージェントはこれを読む（機械可読・決定的）。
  notebook は**同じ関数を呼んで表と図にするだけ**で数値ロジックを持たない（unit の構造検査で機械的に近似担保・§3）。
  両者が同じ関数を使うので、人が見るものとエージェントが読むものはズレない。
- **(b) 実行されない雛形は腐る → E-0001 と同じ水路に載せる。** marimo は純 Python（.py）で、
  `python notebooks/eda.py` が全セルをヘッドレス評価する（marimo 標準の `app.run()`。例外＝非零終了）。
  e2e スモークが合成テーブルで毎回これを叩く（§3）＝「実行される雛形は腐らない」の同型。
  図は「落ちない」だけを検査し画素は比較しない（図でテストが壊れない）。
- **(c) テスト先行・完了＝verify に乗らない → スモークが full（e2e）段階に載る。** checks.toml の
  full=e2e にそのまま追加（軽い：合成数十行＋marimo import。重くなったら slow へ降ろす、が §8 の既定外条件）。
**役割分担**：エージェント＝CLI の YAML（正本・機械可読）／人＝marimo（表・図・対話探索）。
**依存**：`ds` extra に `marimo`・`altair`（polars `df.plot` のバックエンド）を追加。dev group にしない理由：
notebook は DS プロファイルの成果物で ds 抜きでは動かず（polars が要る）、非 DS 案件に marimo を配らない。
`uv sync --extra ds` 1 コマンドで人もエージェントも同じ環境になる。
**プラットフォーム**：marimo/altair は純 Python・スモークは `sys.executable` の subprocess・make 不使用のまま
——Windows を含め既存の非依存性を壊さない。

**判断2. リーク禁止は「規約」でなく「API の形」で守る**（DEC-0007 の clone-per-fold と同じ思想）。
compare/psi は 2 つの DataFrame/Series を受けて各側で独立に集計する——結合してから集計する関数を
このモジュールに置かない。psi のビン境界は train の分位点だけから作る（unit テストで「test を変えても境界不変」を
固定）。drift_auc が結合するのは特徴量列だけで、y は所属ラベル（目的変数はシグネチャに存在しない）。

**判断3. polars/numpy の境界は既存どおり 1 点。** eda/analysis は「表の世界」＝入出力 polars。
指標の数値計算だけ numpy/sklearn（eval 経由）。レポートの正本は polars DataFrame で、YAML は to_dict の写像
（正本を 2 重化しない）。

**判断4. EDA は門番（passes/verify）に載せない。** EDA は調査（事実の記録）で、合否は実験の thresholds が持つ
（「保存は常に許し昇格だけ関門」と同じ分離）。psi 0.25 や auc 0.7 は docstring・スキルに書く「目安」であり、
機械検査にしない（案件の価値判断を土台に焼き込まない）。

**判断5. 指標はレジストリ・EDA は関数。** 「config で選べる種」（指標名）はカタログ＝レジストリにする（DEC-0009）。
EDA の関数群は config の種ではないので、レジストリという儀式は付けず CLI＋スキルを入口にする——
カタログの目的（エージェントが一覧から選ぶ）に対して過不足のない形。

**判断6. 参考リポからの翻訳原則**：クラス（Validator/Analyzer/Calculator）→ 純関数＋frozen dataclass。
print 進捗 → 返り値（構造化レポート）。自前スコア辞書 → METRICS（sklearn）。LightGBM 直書き → MODELS spec。
図 → marimo ビュー内の表示（正本にしない・専用 plot_ モジュールは作らない）。
この翻訳で参考リポの EDA/評価の実質（何を見るか）は全部残る。

## 5. 着手順（歩く骨組み優先・各歩で verify 緑）【改訂2：§9 の追加パーツを織り込み】

1. **済（T-0024）** eval.py：METRICS レジストリ＋回帰/分類の追加指標＋passes の向き対応＋`data metrics`＋
   test_catalog 延長。既存テストの dict 完全一致箇所は部分集合確認へ直し済み。
2. **済（T-0025）** eda.py：profile / target_summary / to_dict＋`uv run data profile`＋eda スキル新設＋
   **notebooks/eda.py 雛形（marimo ビュー）・e2e スモーク・unit 構造検査・ds extra（marimo/altair）**
   （初版手順 5 を吸収して完了。EDA も評価拡張も端まで一巡済み——以降は緑を保った追加のみ）。
3. **T-0026** eda.py：correlations / high_correlation_pairs / compare / psi＋`data compare`、続けて
   drift_auc（run_cv 合成）＋`data compare --auc`＋eda スキルへ「0.7 目安→原因調査」を追記。
   marimo ビューへ compare 表・PSI 表・drift のセルを追加（§2 の予告どおり）。
4. **T-0029（新設）** eda.py の完全性スイープ（§9-1）：profile 延長（skew/kurtosis・IQR 外れ値列・
   datetime 要約・flags）＋ missing_patterns / duplicate_columns / category_target_summary＋
   `data profile` の出力キー延長＋marimo セル追加＋eda スキル追記。
   ——T-0026 とは独立（依存は T-0025 のみ・並行可）。eda.py と同じ入口に足すだけなので T-0026 の直後に置き、
   ファイル・CLI・ビューの文脈を連続させる。
5. **T-0027** analysis.py：segment_metrics / worst_rows / permutation_importance / cv_permutation_importance
   ＋**residual_summary と segment_metrics の residual_mean 列（§9-3）**＋experiment スキルに
   「結果の深掘り」節。drift の原因列特定もここで閉じる。
6. **T-0030（新設）** eval.py の分類予測の深掘り（§9-2）：confusion / class_metrics / calibration_table /
   threshold_table＋experiment スキル「結果の深掘り」節へ分類の並び
   （混同行列→クラス別→較正→閾値表）を追記。——純関数のみ・unit で完結する軽い歩。
7. **T-0028** 回帰経路：run_experiment(task=)＋MODELS に ridge＋回帰の統合テスト（指標の死蔵防止。
   E-0001 は無変更のまま）。統合テストで residual_summary / segment_metrics(residual_mean) を
   OOF に対して 1 回呼び、回帰のエラー分析まで端で通す（期待値は §9-6 の構成から導出）。

タスク分割の目安（DEC-0009「部品と入口は 1 タスク」）：3＝T-0026、4＝T-0029、5＝T-0027、6＝T-0030、7＝T-0028。
T-0029 の依存は T-0025 のみ・T-0030 の依存は T-0024 のみ（どちらも他タスクと並行可。既定の順は上のとおり）。

## 6. 追加した部品と根拠（一覧）

| 部品 | 作る/使う | 根拠（DEC-0008 の判定） |
|---|---|---|
| METRICS レジストリ＋passes 向き | 作る（薄い接続） | 指標本体は全部 sklearn。「config の名前→関数・向き」の対応表は sklearn に無い（本ハーネスの thresholds/passes 固有） |
| pr_auc / log_loss / rmse / mae / mape / f1 / precision / recall | 使う | sklearn.metrics 素通し（average_precision_score・root_mean_squared_error 等）。縁（単一クラス）だけ吸収 |
| profile / target_summary | 作る（薄い集計） | polars の describe/null_count の束ね。ydata-profiling 等は依存重・出力が人向け HTML で機械検査不能 |
| correlations / high_correlation_pairs | 使う＋束ね | 計算は np.corrcoef 1 回。表への整形だけ書く |
| compare（統計量・カテゴリ差） | 作る | sklearn に「2 標本の列別比較レポート」は無い。リーク禁止を API 形状で守るのが固有価値 |
| psi | 作る（約 20 行） | PSI は標準ライブラリに実装が無い（業界標準指標だが sklearn/scipy 非搭載）。ビン境界 train 限定が固有 |
| drift_auc | 合成（ほぼ作らない） | 分類器・CV・AUC は全部既存部品（build_estimator/run_cv/eval）。結合とラベル付けの 20 行だけ |
| segment_metrics / worst_rows | 作る（薄い） | sklearn に group-by 指標は無い。計算は evaluate へ委譲し polars group_by で回すだけ |
| permutation_importance（polars 版） | 作る（約 30 行） | sklearn.inspection 版は numpy/pandas 前提で polars/list 列入力の Pipeline に入らない（＝隙間）。指標は METRICS 委譲 |
| cv_permutation_importance | 作る（薄い） | 「OOF で解釈する」規律を引数の形にする入口。fold ループ 10 行 |
| MODELS の ridge | 使う（工場 1 行） | 回帰指標を死蔵にしないための最小の回帰モデル。DEC-0006 の想定どおりの追加口 |
| notebooks/eda.py（marimo 雛形） | 作る（ビュー 1 本・数値ロジック無し） | 「人が表・図で見る」層は sklearn/polars に無い。正本関数を呼ぶだけ＝二重実装なし。腐り防止は e2e スモーク（E-0001 と同型） |
| marimo・altair（ds extra へ依存追加） | 使う | 表示・描画を再発明しない。altair は polars `df.plot` の標準バックエンド。dev group でなく ds extra（§4 判断1） |

## 7. あえて作らない（sklearn 十分 / Rule of Three / 目的不適合）

- **jupyter（.ipynb）**：導入しない。JSON 形式で diff・ruff/mypy・`python` 直実行のどれにも乗らない。
  ノートブックは marimo の純 .py 1 本だけ（§4 判断1【改訂】で導入済み。2 本目の雛形は作らない）。
- **汎用の図生成モジュール（参考リポ visualizer.py の plot_ 群）**：据え置きで作らない。図は marimo セル内で
  polars `df.plot`／altair をその場で書く（雛形に最小の例だけ置く）。再開条件：人向け報告で**保存図**が
  2 回求められたら、results/ へ PNG を保存する薄い helper を検討（Rule of Three。門番には載せない・§8-1）。
- **notebook 内の独自集計・指標計算・結論記述**：作らない。ビューは harness.ds の関数を呼ぶだけ
  （unit の構造検査で担保・§3）。結論は調査単位の results/ の YAML（既存の done 検査が効く）。
- **`marimo export html` の verify 接続**：スモークは `python` 直実行で足りる（export はレンダリング依存が
  増えるだけで検査が増えない）。HTML 化は共有が要る案件での手動操作（§8-3）。
- **KS 検定・カイ二乗検定など検定群**：PSI＋drift_auc で段階1の分布差検出は足りる。要るときは
  scipy.stats.ks_2samp が 1 行（作るものが無い）。2 回目の必要が出たら compare に列を足す。
- **sklearn.inspection.permutation_importance の直接使用**：上表のとおり polars 入力で不成立（判定済み）。
  逆に **calibration_curve・roc_curve・precision_recall_curve は sklearn をそのまま呼ぶ**（包まない。
  必要になった実験でその場で 1 行）。
- **モデル固有の重要度（LightGBM gain/split・logreg coef_ の包み）**：LightGBM 導入時（宣言済みの保留）に検討。
  coef_ は sklearn の属性を直接読めば足りる。
- **Youden's J の閾値選択**：EP-06 DESIGN B-1 で不採用決定済みのまま。
- **参考リポ eda/location.py（測地距離）**：ドメイン固有。必要な案件で FeatureBlock として作る。
- **classify_cardinality / target_encoding_potential（参考リポ categorical.py）**：前者は profile の n_unique 列から
  エージェントが判断できる（閾値 10/50 の焼き込みは不要）。後者は「実験で確かめる」が本プロジェクトの型
  （効果の予測でなく E-xxxx で検証）。
- **ErrorAnalyzer / FeatureImportanceAnalyzer / AdversarialValidator のクラス構造・派生 API
  （normalize・累積重要度・削除候補・進捗 print）**：純関数＋DataFrame 返しで足りる。加工は polars で。
- **EDA レポートの HTML/固定文書化・レポート保存の専用 store 層**：レポートは調査単位の results/ に YAML
  （既存の「done に結果必須」検査が効く）。専用の保存形式は 2 案件目まで作らない。
- **`data profile` の生 CSV 直読み**：データは store（テーブル定義で検証済み）を通る、の規律を破る口を作らない。

## 8. 残した業務判断＝既定＋上書き条件

1. **図の扱い**——既定：marimo ビュー内の対話表示のみ（正本は構造化レポートの YAML・図は保存しない）。
   上書き条件：人向け報告で**保存図（PNG）**が 2 回求められた案件では、results/ へ保存する薄い描画 helper を
   足す（門番には載せない・§7）。
2. **回帰経路（手順 8）を今回のタスク列に含めるか**——既定：含める（ridge 1 行＋統合テスト。回帰指標を
   「入口の無い部品」にしないため・DEC-0009）。上書き条件：当面の案件が分類のみと決まっているなら手順 8 を
   保留し、METRICS の回帰項目は unit テストとカタログ表示のみで持つ（config から選べるが実験経路は未接続、と
   `data metrics` の説明文に明記する）。
3. **notebook の HTML 共有**——既定：しない（見る人は `uv sync --extra ds` の環境で
   `uv run marimo run <コピー>` を開く。成果物は増やさない）。上書き条件：閲覧者が Python 環境を持たない
   案件では、`marimo export html` の出力を調査単位の results/ に成果物として置く（手動・門番外）。
4. **notebook スモークの段階**——既定：e2e（full 段階。合成数十行＋marimo import で軽い想定）。
   上書き条件：実測で full が体感を損なうほど遅くなったら `slow` マーカーへ降ろし、代わりに
   「import＋セル定義だけの unit」を残す（腐り検知の水路は切らない）。

（drift_auc の調査目安 0.7・PSI の目安 0.1/0.25・psi_bins=10・max_categories=50 は設計側で既定を決めた。
いずれも引数/docstring の目安であり門番ではないため、案件ごとの上書きは引数 1 つ。）

## 9. 完全性スイープ（追加パーツ）【改訂2】

業界標準の EDA・エラー分析と参考リポ全体（profiler/categorical/threshold/error_analysis）を §1〜§8 に
突き合わせ、段階1（ローカル完結・二値分類/回帰）で**汎用的に要る隙間**だけを足す。原則は同じ：
sklearn に在るものは薄く用意（写経しない）・正本は構造化レポート・リーク禁止は API の形・図は marimo の中だけ。
**すべて延長のみ**（既存の関数・CLI・テストの数値期待値は不変。増えるのは列とキーと関数）。

### 9-1. eda.py の延長（T-0029）——テーブル品質の残りを 1 入口（data profile）に集約

**(a) profile の numeric に列を追加**（additive・既存列は不変）：

```python
# numeric の列を延長: column, mean, std, min, q25, median, q75, max,
#                     skew, kurtosis,                      # polars Series.skew()/kurtosis()（使う）
#                     iqr_lower, iqr_upper,                # q25−1.5·IQR / q75＋1.5·IQR（Tukey の柵）
#                     n_outliers, outlier_ratio            # 柵の外の件数と割合
```

外れ値は **IQR 法のみ**（分位はすでに計算済み＝算術 4 行。z-score 法は作らない——正規前提で情報が重複。
2 つ目の必要が出たら method= 引数を検討・Rule of Three）。sklearn の IsolationForest 等「学習する外れ値検出」は
EDA の要約には過剰（必要な案件で FeatureBlock/実験として扱う）。

**(b) TableProfile にフィールドを追加**（to_dict のキーは末尾に追加・キー順固定は維持）：

```python
@dataclass(frozen=True)
class TableProfile:
    ...  # 既存フィールドは不変
    datetime: pl.DataFrame  # column, min, max, n_unique（Date/Datetime 列のみ・無ければ 0 行）
    flags: pl.DataFrame     # column, flag, detail（怪しい列の機械可読な一覧・0 行なら異常なし）
```

flags の値（この 4 種だけ・造語なし）：
- `all_null`：全行欠損（null_ratio==1.0）
- `constant`：一意数 1（学習に寄与しない）
- `quasi_constant`：最頻値の比率 >= quasi_constant_ratio（既定 0.99・profile の引数で上書き）
- `id_like`：一意数 == 行数 かつ Int/String（識別子疑い。特徴量に入れると過学習・リークの温床）

判定材料（null_ratio・n_unique・top_ratio）は既存の集計をそのまま読む＝再計算しない。
sklearn.feature_selection.VarianceThreshold を使わない理由（DEC-0008 の判定）：fit API・数値限定で
「テーブルの報告」に合わない。ここは polars の集計値を見るだけの隙間（約 20 行）。

**(c) 独立関数 3 つ**（TableProfile に入れない理由：行方向のパターン（欠損）・列ペア（重複）・目的変数が要る
（カテゴリ×目的）で、1 テーブル 1 列の要約と形が違う。CLI では同じ `data profile` の出力キーとして同居させる）：

```python
def missing_patterns(df: pl.DataFrame, *, top: int = 20) -> pl.DataFrame:
    """欠損の同時発生パターン。列 = columns（欠損している列名の list・列順）, count, ratio。count 降順・上位 top。
    「どの列がまとまって欠けるか」（同一原因の欠損・結合漏れ）を行単位で見る。
    実装は is_null() を束ねて group_by するだけ（polars 1 式）。全列非欠損の行は columns=[] の行として出る。"""

def duplicate_columns(df: pl.DataFrame) -> pl.DataFrame:
    """内容が同一の列ペア。列 = column, duplicate_of（df で先に現れた列名）。0 行なら重複なし。
    null 同士は等しいとみなす（eq_missing）。列ごとのハッシュで候補を絞ってから全比較（全ペア総当たりを避ける）。
    片方を落とす判断はエージェント/実験側（ここは事実の報告だけ・門番にしない）。"""

def category_target_summary(
    df: pl.DataFrame, *, target: str, columns: Sequence[str] | None = None,
    max_categories: int = 50, top: int = 20,
) -> pl.DataFrame:
    """カテゴリ×目的変数。列 = column, value, count, ratio, target_mean。各列 count 上位 top 値。
    分類なら target_mean＝そのカテゴリの陽性率・回帰なら平均（参考リポ get_category_target_stats の翻訳）。
    columns 省略時は profile と同じ規準のカテゴリ列（target は除く）。
    リーク疑いの読み口も兼ねる：件数の多いカテゴリで target_mean が 0/1 に張り付いていたら要調査
    （docstring とスキルに目安として書く・門番にしない）。専用のリーク検出関数は作らない
    （数値列の極端相関は correlations の上位で同様に読める）。"""
```

**入口**：`uv run data profile` の出力キーに `flags` / `missing_patterns` / `duplicate_columns` を追加、
`--target` 指定時は `category_target_summary` も追加（新 CLI は作らない＝1 テーブルの点検は 1 コマンドのまま）。
eda スキル手順 2 に「flags と duplicate_columns が空でないときは扱いを決めてから先へ」
「--target 時は category_target_summary で張り付き（リーク疑い）を見る」を追記。

**marimo セル（notebooks/eda.py へ追加・すべて同じ関数を呼ぶだけ）**：
「品質フラグ」（prof.flags 表）／「欠損の同時発生」（missing_patterns 表）／「重複列」（duplicate_columns 表）／
「日時列」（prof.datetime 表・0 行でも落ちない）／target 指定時「カテゴリ×目的変数」
（category_target_summary 表＋target_mean の棒グラフ）。数値統計のセルは列が増えるだけで無変更。

**互換への影響（明示）**：tests/test_ds_eda.py の `test_profile_to_dict_is_serializable` はキー並びの完全一致を
見ているため、期待リストの**末尾に新キーを足して更新**する（キー順固定という仕様の検査なので完全一致のまま。
数値の期待値は一切変えない）。CLI YAML・prof.numeric の列は追加のみ。

### 9-2. eval.py の延長（T-0030）——分類予測の深掘り（すべて y_true/y_score の純関数・sklearn 素通し）

```python
def confusion(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> dict[str, int]:
    """混同行列の要約 {tn, fp, fn, tp}。sklearn.metrics.confusion_matrix(labels=[0,1]) の dict 化のみ
    （単一クラスでも 4 キーが揃う）。率（tpr 等）は evaluate/class_metrics が持つ＝二重に返さない。"""

def class_metrics(y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, threshold: float = 0.5) -> pl.DataFrame:
    """クラス別指標（classification_report 相当の機械可読版）。列 = class, count, precision, recall, f1。
    precision_recall_fscore_support(labels=[0,1], zero_division=0) 素通し。文字列レポートは作らない
    （表が正本・エージェントが読める）。evaluate との違い：evaluate は陽性クラスの値だけ・こちらは両クラス。"""

def calibration_table(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *,
    bins: int = 10, strategy: Literal["uniform", "quantile"] = "uniform",
) -> pl.DataFrame:
    """確率の較正（reliability）の表。列 = bin, mean_predicted, fraction_positive, count。
    sklearn.calibration.calibration_curve 素通し＋ビン件数を足すだけ（curve は件数を返さないが、
    件数が無いとビンの信頼度を読めない）。mean_predicted ≒ fraction_positive なら較正されている。
    strategy="quantile" はスコア分位で切る＝デシル表を兼ねる（lift/gain の代替。§9-4）。"""

def threshold_table(
    y_true: NDArray[np.int_], y_score: NDArray[np.float64], *, thresholds: Sequence[float] | None = None
) -> pl.DataFrame:
    """閾値スイープ表。列 = threshold, precision, recall, f1, tp, fp, fn, tn。
    省略時の閾値は既存 _curve（precision_recall_curve）のものをそのまま＝select_threshold_* と同じ土台
    （選ばれた閾値の「前後」を人とエージェントが見比べる用。粗くしたければ thresholds を渡す）。
    行の中身は confusion の再利用＝式の二重実装なし。※閾値の「選択」は既存 select_threshold_*（重複させない）。"""
```

置き場は eval.py（予測とラベルだけの純関数＝eval の世界。analysis.py は DataFrame/CVResult が要るもの）。
**入口**：CLI なし（予測データが要るため。analysis と同じ扱い）。experiment スキル「結果の深掘り」節に分類の並び
——confusion（何をどれだけ間違えたか）→ class_metrics（どちらのクラスで弱いか）→ calibration_table
（確率は信じられるか）→ threshold_table（境界を動かすとどうなるか）→ segment_metrics / worst_rows へ——を追記。
すべて OOF/valid で呼ぶ（既存の規律のまま）。marimo ビューには足さない（EDA ビューの範囲外・§9-4）。

### 9-3. analysis.py の延長（T-0027 に同梱）——回帰の残差分析

```python
def residual_summary(y_true: NDArray[np.float64], y_pred: NDArray[np.float64]) -> dict[str, float]:
    """回帰の残差（y_true − y_pred）の要約。mean・std・min・q25・median・q75・max。
    mean が 0 から離れていれば系統的な偏り（過大/過小予測）。分布の形は marimo でヒストグラム表示。
    sklearn の PredictionErrorDisplay は図（matplotlib）で正本にできない＝数表のこれが隙間（numpy 分位のみ）。"""
```

「残差 vs 予測」の傾向は **segment_metrics に regression 時の `residual_mean` 列を 1 本足して**賄う：
`segment_metrics(qcut(y_pred), ...)` で予測値ビン別の rmse/mae と residual_mean が出る（予測レンジごとの
偏りが表で見える）。専用の binned-residual 関数は作らない（参考リポ analyze_by_feature_bins の実質は
「qcut＋segment_metrics」で全部出る——§1-3 の方針の適用そのまま）。

### 9-4. あえて作らない（このスイープで仕分けした分）

- **z-score 外れ値**：IQR 法で足りる（正規前提の重複）。2 つ目の実需で method= を検討。
- **リーク検出の専用関数**：数値は correlations の上位・カテゴリは category_target_summary の張り付きで読める。
  「検出器」を作ると目安（0.99 等）が門番化する——判断はエージェント/人に残す（§4 判断4 と同じ）。
- **lift / gain 表**：calibration_table(strategy="quantile") がデシル表を兼ねる（各分位の陽性率と件数から
  累積は polars の cum_sum 1 式）。施策ターゲティング要件の案件が出たら専用表を検討（§9-5 判断7）。
- **classification_report の文字列出力**：class_metrics（表）が正本。文字列は機械可読でない。
- **較正の修正（CalibratedClassifierCV）**：まず測るだけ。確率値そのものを業務が使う案件で導入検討（§9-5 判断8）。
- **roc_curve / det_curve / precision_recall_curve の包み**：既存 §7 の既決のまま（必要時 sklearn 直 1 行）。
- **SHAP・部分依存（PartialDependenceDisplay）**：段階1は cv_permutation_importance＋worst_rows で
  「どの列・どの行」まで出る。モデル説明の要件が出た案件で検討（LightGBM 保留と同じ棚）。
- **学習曲線（learning_curve）**：sklearn 直 1 行で足り、段階1の改善はデータ量でなく特徴量仮説が先。
- **時系列の季節性・リサンプリング要約**：profile.datetime（期間の min/max）まで。時系列予測の案件が来たら
  時系列 CV（分割設計）ごと別エピック（EDA だけ先回りしない）。
- **欠損ヒートマップの専用 helper（missingno 相当）**：missing_patterns の表で同じ事実が出る。
  図が要る人は marimo セル上の表で足りる（描画 helper は §8-1 の既定のまま作らない）。
- **予測の深掘り用の 2 本目 marimo ノートブック**：作らない（Rule of Three・雛形は 1 本の既定を維持）。
  人向けの予測レビュー（残差図・較正図）が 2 回求められたら検討（§8-1 と同じ流儀）。

### 9-5. 残した業務判断（§8 の続き・既定＋上書き条件）

7. **lift/gain（デシル運用）**——既定：作らない（calibration_table の quantile で代替）。上書き条件：
   「スコア上位 n% にだけ施策を打つ」運用が案件の要件になったら、累積捕捉率（gain）列を持つ専用表を足す。
8. **確率較正の修正**——既定：calibration_table で測って記録するだけ。上書き条件：予測確率そのものを
   業務計算（期待損失・価格付け等）に使う案件では CalibratedClassifierCV を MODELS/実験系の設計で検討。

### 9-6. テスト（期待値はデータ構成から導出・§3 の表へ追記）

| 層 | 対象 | 合否の根拠数値（構成から導出） |
|---|---|---|
| unit | profile.numeric の skew | 対称な構成（例 [1,2,3]）→ skew==0.0 厳密 |
| unit | profile.numeric の IQR 外れ値 | [1..8]＋100 の 9 値 → 柵は分位から手計算・n_outliers==1・outlier_ratio==1/9 |
| unit | profile.flags | 定数列→constant／100 行中 99 行同値→quasi_constant（既定 0.99）／1..n の Int 列→id_like／全 null 列→all_null。健全な列だけの df → flags 0 行 |
| unit | profile.datetime | 構成した日付の min/max が一致。日時列なし → 0 行（落ちない） |
| unit | missing_patterns | 10 行中 {x,y} 同時欠損 3 行・z 単独 2 行・欠損なし 5 行に構成 → 3 パターンの count が 5/3/2 厳密・ratio も導出どおり |
| unit | duplicate_columns | b=a の複製（null 位置も同じ）→ (b, a) の 1 行。null 位置だけ違う列 → 0 行（eq_missing の検査） |
| unit | category_target_summary | A は target 全 1・B は全 0 に構成 → target_mean が A==1.0・B==0.0 厳密・count 降順 |
| unit | confusion | y=[0,0,1,1]・score=[0.9,0.1,0.8,0.2]・閾値 0.5 → tn=fp=fn=tp==1 厳密 |
| unit | class_metrics | 同上の構成 → 両クラスの precision/recall/f1 を手計算値と一致。単一クラス y でも 2 行返り zero_division=0 |
| unit | calibration_table | score 全行 0.3・y は 4 行中 1 が正例 → 1 ビンに count==4・fraction_positive==0.25・mean_predicted==0.3 厳密 |
| unit | threshold_table | y=[0,0,1,1]・score=[0.1,0.4,0.6,0.9] → 各閾値行の P/R/F1/tp..tn を手計算と一致。select_threshold_max_f1 の返す閾値が表の f1 最大行と一致（土台共有の整合検査） |
| unit | residual_summary | y_true=[0,0]・y_pred=[3,4] → mean==−3.5・q25/median 等も構成から厳密 |
| unit | segment_metrics(residual_mean) | セグメント A は残差 +1 固定・B は −1 固定に構成 → residual_mean が A==1.0・B==−1.0 厳密 |
| integration | CLI data profile 延長 | 合成テーブル（定数列・重複列・同時欠損を仕込む）→ YAML の flags/missing_patterns/duplicate_columns が構成と一致。--target で category_target_summary が出る |
| e2e | notebooks/eda.py スモーク | 既存の枠のまま（セルが増えても終了コード 0 のみ検査・変更なし） |

（T-0028 の回帰統合テストに「OOF へ residual_summary / segment_metrics(residual_mean) を 1 回呼ぶ」を足し、
y=2·x1＋雑音の構成から |mean residual| <= 0.1 を確認——回帰のエラー分析まで端で通す。）

### 9-7. 追加パーツと根拠の一覧（§6 の続き・DEC-0008 の判定）

| 部品 | 作る/使う | 根拠 |
|---|---|---|
| profile.numeric の skew/kurtosis | 使う（polars） | Series.skew()/kurtosis() 素通し・列を足すだけ |
| profile.numeric の IQR 外れ値列 | 作る（算術 4 行） | sklearn に「表形式の外れ値要約」は無い（検出器は学習 API で過剰）。分位は計算済み |
| profile.flags（定数/準定数/ID/全欠損） | 作る（約 20 行） | VarianceThreshold は fit API・数値限定で不適。既存集計値の判定だけ |
| profile.datetime（期間の要約） | 使う（polars 集計） | min/max/n_unique の束ね。季節性等はやらない（§9-4） |
| missing_patterns | 作る（polars 1 式） | sklearn/polars に同時発生パターンの既製 API は無い（missingno は図で正本にできない） |
| duplicate_columns | 作る（薄い） | 既製 API 無し。ハッシュで絞って比較するだけ |
| category_target_summary | 作る（group_by 1 式） | sklearn に無い。参考リポ get_category_target_stats の翻訳＋リーク疑いの読み口 |
| confusion | 使う | confusion_matrix(labels=[0,1]) の dict 化のみ |
| class_metrics | 使う | precision_recall_fscore_support 素通し（classification_report の機械可読版） |
| calibration_table | 使う＋束ね | calibration_curve 素通し＋件数列（curve が返さない分だけ足す） |
| threshold_table | 作る（薄い束ね） | 曲線・混同行列は sklearn。閾値×指標の「表」への束ねが隙間。既存 _curve・confusion を再利用 |
| residual_summary | 作る（numpy 分位のみ） | PredictionErrorDisplay は図。数表の要約が隙間 |
| segment_metrics の residual_mean 列 | 延長（1 列） | binned-residual 専用関数を作らないための最小の置き場 |
