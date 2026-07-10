---
id: EP-29
kind: epic
status: todo
plan: outline
requirements: [REQ-001]
depends_on: [EP-27]
created: 2026-07-10
---
# EP-29 統計モデリング（ベイズ）を 5 つ目のプロファイルにする

## 方針：ML の器に押し込まない
`harness/stats/` を独立したプロファイルにする。`Profile(name, pm_checks)` は config 駆動の import なので
`profiles = ["harness.ds", "harness.stats"]` と並記できる。

**共有するもの**（思想と土台）：`Registry`・`storage`・fingerprint・config・`GATES`・区間の作法・
`results/` の作法・台帳の形式・ds のテーブル定義。

**共有しないもの**：sklearn の `Pipeline`・`run_cv`・out-of-fold・`METRICS`・leaderboard・`FORMATS`。
正本は `InferenceData`（netCDF）。点推定の指標で事後分布を要約すると、保存すべきものが壊れる。

## 背骨
宣言 → 事前予測検査 → 推論 → **収束の判定**（`r_hat` / `ess` / divergences）→ 事後予測検査 →
PSIS-LOO による比較 → 採用。

収束の判定に**新しい gate kind は要らない**（独立レビューによる訂正）。`r_hat <= 1.01`・`ess >= 400`・
`divergences <= 0` はどれも「指標 × 閾値 × 向き」の形なので、既存の `value_threshold` の spec が
そのまま書ける。新 kind を登録すると `value_threshold` の二重化になる。stats 側に要るのは、
指標を計算する `BAYES_DIAGNOSTICS` と、その向き（`higher_is_better`）の表だけである。
`gates.py` の fail closed（有限性の検査）は発散したサンプリングに対してそのまま働く。

## 軸（レジストリ）
`BAYES_MODELS`・`SAMPLERS`・`BAYES_DIAGNOSTICS`・`PPC_CHECKS`。

`SAMPLERS` の既定は nutpie。ただし**PyMC 既定サンプラーへのフォールバックが必須**：nutpie は離散潜在
変数を含むモデルを引けない（compound step が要る）。「nutpie が最速」はこのリポジトリでは未実測なので、
既定に選ぶ根拠は PyMC 公式の推奨であることを明記する（速さを主張するなら測ってから書く）。

`PRIORS` / `FAMILIES` は軸**でない**（モデル宣言のパラメータであって、名前 → 工場の解決点が無い。
正本は PyMC / bambi の名前空間）。

## Python 3.14 に載るか（2026-07-10 実測）
nutpie 0.16.11 に cp314 wheel あり。pytensor 3.1.2 も cp314 あり（`>=3.12,<3.15`）。pymc 6.1.0 と
arviz 1.2.0 は pure-python。**スタックは 3.14 に載る**ので、EP-29 は T-0188（環境の軸）に依存しない。

## 作らないもの
**MCMC から `MODELS` へのブリッジ**。事後分布を点推定に潰すので、保存すべきものが壊れる。橋が要るなら
データ層に架ける。

ただし「PSIS-LOO が既にその目的を満たしている」というのは**過大主張だった**（独立レビューによる訂正）。
PSIS-LOO が比べられるのはベイズモデル同士だけである。**ds の champion（GBM 等）と統計モデルの
どちらを配信するか**は PSIS-LOO では決められず、共通のホールドアウトで事後予測の点要約を採点する
しかない。ブリッジを作らない判断は維持するが、その代償は「プロファイルを跨ぐモデル比較ができない」
ことだと正直に書いておく。跨ぐ比較が実際に要ると分かった時点で、この判断を見直す。

## verify での扱い
MCMC は遅い。極小モデル・少 draw の `--test`（小さなスモーク）を必須にし、`uv run verify` に接続する
（実験スクリプトの規約と同じ）。

## ds に属するもの（間違えない）
解析的ベイズ（`BayesianRidge` / `ARDRegression` / `GaussianProcessRegressor`）は sklearn の契約に
完全準拠するので、ds の `MODELS` の天然の住人。stats プロファイルには入れない。
