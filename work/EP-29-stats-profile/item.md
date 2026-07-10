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
PSIS-LOO による比較 → 採用。収束の判定は `GATES` に登録する（3 人目以降の住人。中核は変えない）。

## 軸（レジストリ）
`BAYES_MODELS`・`SAMPLERS`（既定は nutpie＝実測で最速）・`BAYES_DIAGNOSTICS`・`PPC_CHECKS`。

`PRIORS` / `FAMILIES` は軸**でない**（モデル宣言のパラメータであって、名前 → 工場の解決点が無い。
正本は PyMC / bambi の名前空間）。

## 作らないもの
**MCMC から `MODELS` へのブリッジ**。「同じ out-of-fold で比較したい」という目的は PSIS-LOO が既に
満たしており、ブリッジは保存すべき事後分布を点推定に潰す。橋が要るならデータ層に架ける。

## ds に属するもの（間違えない）
解析的ベイズ（`BayesianRidge` / `ARDRegression` / `GaussianProcessRegressor`）は sklearn の契約に
完全準拠するので、ds の `MODELS` の天然の住人。stats プロファイルには入れない。
