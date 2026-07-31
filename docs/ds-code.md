# ds のコード — どのファイルが何を担い、どう組まれているか

`docs/ds.md`（作業の流れとカタログの地図）の姉妹。こちらは**中身の設計**を説明する：`src/harness/ds/` の
各ファイルが何を担うか、内容がどこにどう書かれているかを、コードを読む前につかめるようにする。この文書が実装と
食い違わないことは `code_doc_lint`（`uv run verify`）が保証する＝モジュールを足したのにここで触れていないと
検査が落ちる。

## 設計の 5 つの芯

1. **背骨は scikit-learn のパイプライン**。特徴量→前処理→モデルを 1 本のパイプラインにまとめる。交差検証では
   fold ごとにパイプラインを複製し、**学習に使っていない側だけで予測(OOF)** を作る（`cv.py` の `run_cv`）＝
   データ漏れを構造で防ぐ。自前の学習ループは書かない。
2. **拡張ポイントは「レジストリ」**（名前つきのカタログ）。変わりうる部分（特徴量・エンコーダ・モデル・指標・
   保存形式…）はレジストリに登録し、config は名前で選ぶだけ。一覧コマンドはレジストリから機械生成なので、
   実装と常に一致する。新しい部品は 1 行の登録で、一覧・config・実験のすべてに載る。
3. **やることは「宣言」で決める**。何を学習するかは config（YAML）、テーブルの形は `docs/data/` の YAML、
   モデルの由来（provenance＝どの版・何から作ったか）は保存時の manifest（保存物に付く由来書き＝版・作成元データ・形式などのメタデータ 1 枚）。コードは「読むだけ」で、案件ごとに変えるのは宣言のほう。
4. **業界標準を再発明しない**。指標・データ分割・前処理は scikit-learn、数値計算は numpy。自作するのは
   sklearn に無い隙間だけ（`features.py`）。判断軸は「sklearn が十分うまくやっているか」＝OneHot や PCA など
   sklearn が良くやるものは作らず直接使い、list 列の multi-hot・多キー結合などの隙間だけ作る。
5. **中核とプロファイルの境界**。中核（`src/harness/`）は ds を知らない。ds は config（`profiles=["harness.ds"]`）
   経由でだけ中核に現れる（`profile.py` が `data lint` を verify に載せるだけ）。だから非 DS の案件は
   config 1 行で ds を丸ごと外せる。

## 全体像（流れとファイルの関係）

学習の主経路は左から右へ進む（`①入力 → ③組み立て → ④評価 → ⑤保存`）。`experiment.py` が ③〜⑤ を 1 回で
束ねる指揮者。②探索は主経路の枝、時系列・教師なしは主経路とは別のレジストリ経路。

```text
  ①入力・定義          ③組み立て              ④評価・実験          ⑤保存・採用
  schema.py            features.py            eval.py              models.py
  data.py       ──▶    pipeline.py     ──▶    experiment.py  ──▶   onnx_format.py
  store.py             cv.py / tune.py        （指標・合否）        （保存・champion 昇格）

  ②探索（主経路の枝）  : eda.py・analysis.py
  別経路（別レジストリ）: forecast.py（時系列）・unsupervised.py（教師なし）
  配線                 : cli.py（uv run data の入口）・monitor.py（配信後の分布監視）・
                         scoring.py（配信後の答え合わせ）・profile.py（verify 結線）
```

## どのコードがどんな役割か

`docs/ds.md` の「学習の流れ」の段と対応する。中身を読まなくても、どこを見れば・どこに足せばよいかが分かる。

**入力・定義**
- `schema.py` … テーブル定義（列・型・キー）の YAML を読み、静的検査と実データ検証を組み立てる（`data lint`）。
- `data.py` … データ源（合成データ・テーブル）の読み込みと固定分割（学習/テストの取り違えを防ぐ）。
- `store.py` … データ実体の保存・読み込み（検証を通ったものだけ保存する）。

**探索**
- `eda.py` … 探索の構造化レポート（`data profile`＝1 表の要約 / `data compare`＝2 群の比較）。
- `analysis.py` … 学習後の深掘り（グループ別の指標・誤差の大きい行・特徴の効き方・回帰の残差）。

**特徴量・モデルの組み立て**
- `features.py` … 特徴量作成の枠組み（`FeatureBlock`＝polars 入→polars 出・sklearn 互換）とレジストリ `BLOCKS`。
- `pipeline.py` … 特徴量→エンコード→モデルの sklearn パイプラインを組み立てる中核（`ENCODERS`/`SELECTORS`/`MODELS`）。
- `cv.py` … 交差検証と固定分割（fold 割当・学習外予測(OOF)・`run_cv`＝fold ごとに clone して train だけで fit）。
- `tune.py` … ハイパラ探索（レジストリ `TUNERS`＝`*SearchCV` でモデルを包む）。

**評価・実験**
- `eval.py` … 指標の算出（scikit-learn）と、宣言した閾値による合否（レジストリ `METRICS`・`passes`）。
- `experiment.py` … 実験の一気通貫（設定→学習→評価→保存をつなぐ薄い接着＝`run_experiment`）。

**保存・採用（champion）**
- `models.py` … 学習済みモデル（sklearn パイプライン丸ごと）の保存・読み込み・一覧・昇格（`promote_model`・
  保存形式 `FORMATS`）。読み込みは manifest の `format` 文字列で分岐する。
- `onnx_format.py` … 可搬な ONNX 保存形式（`FORMATS` の "onnx"。核 `models.py` を肥らせないため別ファイル）。

**別バックボーン経路**
- `forecast.py` … 古典時系列（ARIMA/SARIMA/ETS＝statsmodels・auto_arima＝pmdarima。sklearn 経路とは別・レジストリ `TS_MODELS`）。
- `unsupervised.py` … 教師なし学習（次元圧縮・クラスタリング・異常検知＝`DIMRED`/`CLUSTERERS`/`ANOMALY`）。

**運用・配線**
- `monitor.py` … 配信ログ×学習基準テーブルの分布監視（`data monitor` の中身。純関数）。入力のずれ（psi/drift）＝
  代理指標だけを見る（正解は使わない）。
- `scoring.py` … 配信予測×後から届く実績の答え合わせ（`data score` の中身。純関数）。input_fingerprint で結合し、
  実測指標（eval 委譲）と昇格時の約束との差を band で返す。入力が安定でも正解率が崩れた champion を捉える
  ＝monitor の代理では見えない黙った劣化を塞ぐ経路。門番にしない（exit 0）。
- `cli.py` … `uv run data <サブコマンド>` の入口（typer）。
- `profile.py` … DS プロファイルの宣言（`data lint` を verify に載せる）。中核はこれを config 経由でだけ知る。

## どこに・何が・どう書かれているか（内容の在り処）

「どういう内容がどこにどう書かれているか」を一望する。案件ごとに変えるのは**宣言**（左）で、**コード**（右）は据え置く。

| 内容 | 宣言（案件ごとに書く） | それを扱うコード |
| --- | --- | --- |
| テーブルの形（列・型・キー） | `docs/data/*.yaml` | `schema.py`（検査） |
| 何を学習するか（データ・特徴・モデル・閾値） | 実験フォルダの `config.yaml` | `templates/experiment/train.py`（雛形・触らない） |
| 使える部品の在庫 | —（機械生成） | 各ファイルのレジストリ → `uv run data <一覧>` |
| モデルの由来（provenance＝版・fingerprint〔中身から計算した識別子〕・指標・依存・保存形式） | —（保存時に自動） | `models.py` の manifest（`format` で load 分岐） |
| 採用の合否ライン | `config.yaml` の `thresholds` | `eval.py` の `passes`（champion 昇格の `value_threshold`） |

## 拡張ポイント（新しい部品はレジストリに 1 行）

拡張ポイントはすべてレジストリ。該当ファイルに 1 行登録すれば一覧に載り、config から名前で選べる（登録時に
docstring の 1 行目が説明文になる＝無いとエラー）。config の具体的な書き方は experiment / features スキルへ。

| 足すもの | ファイル: レジストリ | 一覧コマンド |
| --- | --- | --- |
| 特徴量ブロック | `features.py`: `BLOCKS` | `data blocks` |
| エンコーダ（値の変換） | `pipeline.py`: `ENCODERS` | `data encoders` |
| モデルの種類 | `pipeline.py`: `MODELS` | `data models` |
| 特徴選択 | `pipeline.py`: `SELECTORS` | `data selectors` |
| ハイパラ探索 | `tune.py`: `TUNERS` | `data tuners` |
| 評価指標 | `eval.py`: `METRICS` | `data metrics` |
| データ源 | `data.py`: `DATA_SOURCES` | `data sources` |
| 保存形式 | `models.py`/`onnx_format.py`: `FORMATS` | `data formats` |
| 時系列モデル | `forecast.py`: `TS_MODELS` | `data models`（[timeseries] 群） |
| 教師なし（圧縮/クラスタ/異常） | `unsupervised.py`: `DIMRED`/`CLUSTERERS`/`ANOMALY` | `data unsupervised` |
