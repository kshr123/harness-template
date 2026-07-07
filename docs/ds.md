# ds — データサイエンス（表データの学習）のプロファイル

表形式のデータからモデルを学習し、評価して、採用版（champion）に選ぶまでを支える一式のプロファイル。
用意済みの部品（特徴量・モデル・評価指標・交差検証など）を設定ファイル（config）で組み合わせて実験を回し、
学習コードそのものは書かない。この基盤で機械学習の実験・モデル作りをする人が、**何があり・どこを見ればよいか**を
つかむための地図（この 1 枚）。手順そのものや細かい契約は、ここからリンクする各正本に置く（ここには再掲しない）。

実装は `src/harness/ds/`。依存は `uv sync --extra ds` で入れる。設計の芯は「業界標準を再発明しない」：
評価指標・交差検証（データを分けて繰り返し評価する方法）・前処理は scikit-learn、数値計算は numpy を使い、
config で差し替えるのは**モデルの種類**と**保存形式**だけ。

## 学習の流れ（全体像→どこにあるか）

1. **テーブルを定義する** … 列・型・キーを YAML で書く。置き場は `docs/data/`。一覧 `uv run data list`、
   定義の検査 `uv run data lint`。
2. **データを見る（探索）** … 1 つの表の要約は `uv run data profile`、2 群の比較は `uv run data compare`。
   進め方は eda スキル（`.claude/skills/eda/`）。
3. **特徴量を組む** … 特徴量ブロックとエンコーダ（値の変換）を config で選ぶ。使えるものの一覧は
   `uv run data blocks` / `uv run data encoders`。新しく作るか既存を使うかの判断は features スキル。
4. **実験する** … 仮説ごとに config を 1 つ書き、実験の雛形（`templates/experiment/`）が
   「設定 → 学習 → 評価 → 保存」を一気に回す。config に書けるモデル・特徴選択・ハイパラ探索・評価指標の一覧は
   `uv run data models` / `data selectors` / `data tuners` / `data metrics`。データ源は `uv run data sources`。
   手順は experiment スキル。
5. **変種を比べて選ぶ** … 変種ごとの結果を集めた表（リーダーボード）は `uv run data experiments`。
   合否は config で宣言した閾値（合格ライン）で決める。
6. **保存して champion に採用する** … champion＝現在採用している版。採用は 2 つの合否判定を両方満たしたときだけ：
   絶対（宣言した閾値を満たす）と相対（今の champion に主要指標で勝つ）。保存済みの一覧は
   `uv run data saved`（champion に ★）。保存形式は既定が pickle、可搬な ONNX は `uv run data formats`。
7. **配信する / まとめて予測する** … 実時間の予測 API は serve プロファイル（`docs/serve.md`）。
   保存済みテーブルへ一括で予測を出すバッチ推論は `uv run data predict`。
8. **監視する** … 配信後の分布のずれ（ドリフト）の監視は `uv run data monitor`。ずれの大きさは
   安定/要注意/大変化の 3 段で読む。再学習まで含む運用の閉ループは ops プロファイル（`docs/ops.md`）。

このほかの部品：教師なし学習（クラスタリング・埋め込み・異常検知）は
`uv run data unsupervised` / `cluster` / `embed` / `anomaly`。時系列予測は `src/harness/ds/forecast.py`。

## ディレクトリ構成（`src/harness/ds/`）

各ファイルは 1 つの役割を持つ（上の「学習の流れ」の段と対応）。中身を読まなくても、どこを見れば・どこに
足せばよいかが分かるようにしておく。

**入力・定義**
- `schema.py` … テーブル定義（列・型・キー）の YAML を読み、静的検査と実データ検証を組み立てる（`data lint`）。
- `data.py` … データ源（合成データ・テーブル）の読み込みと固定分割（学習/テストの取り違えを防ぐ）。
- `store.py` … データ実体の保存・読み込み（検証を通ったものだけ保存する）。

**探索**
- `eda.py` … 探索の構造化レポート（`data profile`＝1 表の要約 / `data compare`＝2 群の比較）。
- `analysis.py` … 学習後の深掘り（グループ別の指標・誤差の大きい行・特徴の効き方・回帰の残差）。

**特徴量・モデルの組み立て**
- `features.py` … 特徴量ブロックの枠組み（レジストリ `BLOCKS`）。
- `pipeline.py` … 特徴量→エンコード→モデルの scikit-learn パイプラインを組み立てる中核（`ENCODERS`/`SELECTORS`/`MODELS`）。
- `cv.py` … 交差検証と固定分割（fold 割当・学習外予測(OOF)・`run_cv`。データ漏れの無い評価）。
- `tune.py` … ハイパラ探索（レジストリ `TUNERS`＝`*SearchCV` でモデルを包む）。

**評価・実験**
- `eval.py` … 指標の算出と、宣言した閾値による合否（レジストリ `METRICS`・`passes`）。
- `experiment.py` … 実験の一気通貫（設定→学習→評価→保存をつなぐ薄い接着＝`run_experiment`）。

**保存・採用（champion）**
- `models.py` … 学習済みモデルの保存・読み込み・一覧・昇格（`promote_model`・保存形式 `FORMATS`）。
- `onnx_format.py` … 可搬な ONNX 保存形式（`FORMATS` の "onnx"）。

**別バックボーン経路**
- `forecast.py` … 古典時系列（ARIMA/SARIMA/ETS＝statsmodels。sklearn 経路とは別・レジストリ `TS_MODELS`）。
- `unsupervised.py` … 教師なし学習（次元圧縮・クラスタリング・異常検知＝`DIMRED`/`CLUSTERERS`/`ANOMALY`）。

**運用・配線**
- `monitor.py` … 配信ログ×学習基準テーブルの分布監視（`data monitor` の中身）。
- `cli.py` … `uv run data <サブコマンド>` の入口（typer）。
- `profile.py` … DS プロファイルの宣言。中核は config（`profiles = ["harness.ds"]`）経由でだけこれを知り、
  `data lint` を verify に載せる。

## 拡張のしかた（新しい部品はレジストリに 1 行）

差し替え口はすべて**レジストリ**（機械可読のカタログ）。新しい部品は下の該当ファイルのレジストリに 1 行
登録すると、一覧コマンドに自動で載り、config から名前で選べるようになる（一覧を手で書かない＝実装と常に
一致する）。登録時に docstring の 1 行目が説明文になるので必ず書く（無いとエラーで登録できない）。手順は
features / experiment スキル。「作るか、sklearn で足りるか」の判断も features スキルにある。

| 足したいもの | どこに（ファイル: レジストリ） | 一覧コマンド | config での選び方 |
| --- | --- | --- | --- |
| 特徴量ブロック | `features.py`: `BLOCKS` | `data blocks` | `features` 節 |
| エンコーダ（値の変換） | `pipeline.py`: `ENCODERS` | `data encoders` | `encode` 節 |
| モデルの種類 | `pipeline.py`: `MODELS` | `data models` | `model` 節 |
| 特徴選択 | `pipeline.py`: `SELECTORS` | `data selectors` | `select` 節 |
| ハイパラ探索 | `tune.py`: `TUNERS` | `data tuners` | `model` 節の `tune:` |
| 評価指標 | `eval.py`: `METRICS` | `data metrics` | `thresholds` |
| データ源 | `data.py`: `DATA_SOURCES` | `data sources` | `data` 節 |
| 保存形式 | `models.py`/`onnx_format.py`: `FORMATS` | `data formats` | `save_model` の `format` |
| 時系列モデル | `forecast.py`: `TS_MODELS` | `data models`（[timeseries] 群） | `model` 節（`task: timeseries`） |
| 教師なし（圧縮/クラスタ/異常） | `unsupervised.py`: `DIMRED`/`CLUSTERERS`/`ANOMALY` | `data unsupervised` | 各コマンドの引数 |

## もっと知りたいとき（各正本への案内）

- **進め方・考え方**（端まで通る最小の実装を先に作る、実験の回し方の思想）… `docs/method.md`。
- **手順（How-to）** … experiment（実験の回し方）・eda（探索）・features（特徴量の足し方）の各スキル。
- **テーブル定義の書き方・置き場** … `docs/data/`（定義の YAML）と `uv run data lint`。
- **部品の一覧はコマンドから見る**（このページに書き写さない）… `uv run data --help` が窓口。一覧は機械が
  カタログから生成するので、常に実装と一致する。

配信・運用まで含めた位置づけ：ds で作った champion を serve が配信し（`docs/serve.md`）、ops が
CI・再学習・監視の閉ループでまわす（`docs/ops.md`）。ds はその最初の「モデルを作って選ぶ」ところを担う。
