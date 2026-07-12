---
id: T-0213
kind: task
status: done
title: BAYES_MODELS と SAMPLERS（nutpie 既定・PyMC フォールバック）で推論を一巡させる（walking skeleton）
created: 2026-07-11
depends_on: [T-0212]
verified_by:
  - tests/test_stats_inference.py::test_linear_recovers_known_coefficients
  - tests/test_stats_inference.py::test_inference_is_deterministic
  - tests/test_stats_inference.py::test_nutpie_falls_back_to_pymc_for_discrete_latents
  - tests/test_stats_inference.py::test_registries_are_populated
---
## 実装（done・2026-07-13）
- models.py（BAYES_MODELS：normal_mean・linear／build_bayes_model・data→pm.Model 契約）と sampling.py
  （SAMPLERS：nutpie 既定・pymc／run_inference／離散潜在で nutpie→pymc 自動フォールバック・警告つき）。
- 少 draw の smoke（draws/tune=150・chains=2・~5s）で既知係数の回復・決定性・フォールバックを verify に接続。
- docs/stats.md にコードの役割を追記（code_doc_lint）。

# T-0213 宣言 → 推論 → InferenceData の最小の一巡

## 何が問題か
背骨（宣言 → 推論 → 収束判定 → 事後予測検査 → 比較 → 採用）の最初の 2 段が無い。
着手は全体→詳細の規約どおり、極小モデルで端まで通る骨組みを先に作る。

## やること
- `BAYES_MODELS: Registry[Entry]`：config の kind → PyMC モデルを組み立てる工場。最初の住人は極小の
  正規線形回帰 1 つだけ（骨組みなので住人を増やさない）。kind は PyMC / 統計の標準語彙の写しなので
  `require_source` は不要（GATES と違い、名前は既に外にある）。
- `SAMPLERS: Registry[Entry]`：既定は nutpie。**PyMC 既定サンプラーへのフォールバックが必須**
  （nutpie は離散潜在変数を含むモデルを引けない＝compound step が要る）。どちらで引いたかを
  結果（InferenceData の attrs か戻り値）に必ず記録する（黙って切り替えない）。
  既定に nutpie を選ぶ根拠は PyMC 公式の推奨であり、このリポジトリでの速度は未実測——docstring にそう書く
  （速さを主張するなら測ってから）。
- `run_inference(spec, data, *, draws, tune, chains, seed)` → `InferenceData`。seed は明示引数（グローバルな
  種設定をしない）。
- 極小モデル・少 draw（例 draws=50・chains=2）のスモークテストを `uv run verify` に接続する
  （MCMC は遅い。verify はネットワーク 0・数十秒以内に収める）。

## やらないこと
- 収束判定（T-0214）・保存（T-0215）・PPC（T-0216）・比較と採用（T-0217）・CLI（T-0218）。
- `PRIORS` / `FAMILIES` のレジストリ化（軸でない。モデル宣言のパラメータで、正本は PyMC の名前空間）。
- ds の `MODELS` へのブリッジ（作らない。解析的ベイズは ds の `MODELS` の住人で、ここに入れない）。

## 受け入れ基準
- 既知の生成過程（例 `y = 2x + 1 + noise`、seed 固定）で作ったデータに対し、事後平均が真の係数を含む
  広い区間に入る（期待値はデータの生成方法から導く。実装出力の写経をしない）。
- 同じ `(spec, data, seed)` で 2 回走らせると同じ結果（決定性。nutpie・PyMC どちらの経路でも）。
- 離散潜在変数を含む極小モデルで、nutpie 既定のまま完走し、フォールバックしたことが記録に残る
  （別の立場が「どのサンプラーで引いたか」を結果から読める）。
- `uv run verify` 全成功（スモークが verify に接続されている）。
