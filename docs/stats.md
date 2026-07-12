# stats プロファイル（ベイズ統計モデリング）

`harness.stats` は統計モデリング（ベイズ推論）を扱うプロファイル。ML（ds）の器に押し込まず、独立した
プロファイルとして config に並記する（`profiles = ["harness.ds", …, "harness.stats"]`）。有効化には
`uv sync --extra stats`（pymc・nutpie・arviz＋netCDF 保存の h5netcdf・h5py）が要る。

## なぜ ds に入れないか
点推定の指標（accuracy・rmse）で事後分布を要約すると、保存すべきもの（分布・不確実性）が壊れる。ベイズは
「1 点の予測」ではなく「事後分布」を出すので、sklearn の Pipeline／交差検証／out-of-fold／leaderboard の
枠に素直に載らない。だから別バックボーンにする（ds の forecast.py が古典時系列を別経路にするのと同じ判断）。

なお解析的ベイズ（`BayesianRidge`・`ARDRegression`・`GaussianProcessRegressor`）は sklearn の契約に完全準拠する
ので **ds の `MODELS` の住人**であって、stats には入れない（間違えない）。stats が扱うのは MCMC（pymc）で
事後分布をサンプリングするモデル。

## ds と共有するもの（土台と思想）
- `Registry`（kind → 工場の共通形）・`storage`（保存の抽象）・fingerprint（中身から計算する短い識別子）。
- config の読み方・`GATES`（昇格の判定レジストリ）・区間の作法・`results/` の作法・台帳の形式。
- 昇格の中核（`harness.promotion`）＝採用の経路は 3 つ目の複製を作らず ds/serve と同じものを使う。

## ds と共有しないもの
- sklearn の `Pipeline`・`run_cv`・out-of-fold・`METRICS`・leaderboard・`FORMATS`。
- 保存の正本は **`InferenceData`（netCDF）**。点推定へ潰さない（潰すと分布が消える）。

## 背骨（宣言 → 推論 → 判定 → 採用）
宣言（モデル・事前分布）→ 事前予測検査 → 推論（MCMC）→ **収束の判定**（`r_hat` / `ess` / divergences）→
事後予測検査 → PSIS-LOO による比較 → 採用。収束の判定に新しい gate kind は要らない（`r_hat <= 1.01` 等は
どれも「指標 × 閾値 × 向き」で既存の `value_threshold` の spec がそのまま書ける）。stats に要るのは指標を
計算するレジストリ（`BAYES_DIAGNOSTICS`）と、その向き（`higher_is_better`）の表だけ。

## サンプラーの既定
`SAMPLERS` の既定は nutpie（PyMC 公式の推奨に基づく。速さの主張は未実測なので根拠は「公式推奨」と明記）。
ただし PyMC 既定サンプラーへの**フォールバックが必須**（nutpie は離散潜在変数を含むモデルを引けない＝
compound step が要る）。

## プロファイル跨ぎのモデル比較はできない（正直な限界）
PSIS-LOO が比べられるのはベイズモデル同士だけ。**ds の champion（GBM 等）と統計モデルのどちらを配信するか**は
PSIS-LOO では決められず、共通のホールドアウトで事後予測の点要約を採点するしかない。MCMC から `MODELS` への
ブリッジは作らない（事後分布を点推定に潰すため）。跨ぐ比較が実際に要ると分かった時点でこの判断を見直す。

## コードの役割（src/harness/stats/）
- `models.py` … ベイズモデルのレジストリ `BAYES_MODELS`（kind →「データから pm.Model を組む工場」）。
  sklearn の MODELS と違い構築時に観測データを抱く（`(data, **params) → pm.Model`）。住人は normal_mean・linear。
  `build_bayes_model(spec, data)` が config の model 節から 1 つ組む。
- `sampling.py` … サンプラーのレジストリ `SAMPLERS`（nutpie＝既定・pymc）と推論の一巡 `run_inference`。
  離散潜在があれば nutpie→pymc へ自動フォールバック（`resolve_sampler`・警告つき・fail closed）。決定性は seed。
- `diagnostics.py` … 収束診断のレジストリ `BAYES_DIAGNOSTICS`（r_hat・ess_bulk・divergences）と向きの表。
  `assess_convergence(idata, thresholds)` が既存の `gates.value_threshold` で合否を出す（新 gate kind なし・
  fail closed＝発散して非有限なら不合格）。

## 3.14 での依存（2026-07-13 実測）
pymc 6.1.0・nutpie 0.16.11・arviz 1.2.0・pytensor 3.1.3 が 3.14 で動く（import・サンプリング・診断・netCDF
往復まで確認）。pymc 経由の numba 0.65（cp314 wheel あり）が numpy を 2.4 系に固定し、`uv sync --all-extras`
全体が numpy 2.4 に揃う（他 extra は 2.4 で問題なし）＝環境分割は不要。
