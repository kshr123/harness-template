---
id: T-0214
kind: task
status: done
title: BAYES_DIAGNOSTICS（r_hat・ess・divergences）を既存の value_threshold で判定する（新 gate kind なし）
created: 2026-07-11
depends_on: [T-0213]
verified_by:
  - tests/test_stats_diagnostics.py::test_diagnostic_directions_are_declared
  - tests/test_stats_diagnostics.py::test_converged_model_passes_reasonable_thresholds
  - tests/test_stats_diagnostics.py::test_impossible_ess_threshold_fails_threshold_not_met
  - tests/test_stats_diagnostics.py::test_nonfinite_diagnostic_is_rejected_fail_closed
---
## 実装（done・2026-07-13）
- diagnostics.py：BAYES_DIAGNOSTICS（r_hat＝全変数の max・ess_bulk＝全変数の min・divergences＝総数）と
  DiagnosticEntry.higher_is_better（r_hat/divergences=False・ess_bulk=True）。arviz 1.2 の rhat/ess は DataTree
  なので data_vars を畳んで max/min を取る（実測で API 差を確認）。
- assess_convergence(idata, thresholds)：診断を計算し diagnostic_directions を解決して GateContext に渡し、
  既存 gates.value_threshold の並びで合否（**新 gate kind なし**）。fail closed＝非有限（発散）は not_finite で不合格。


# T-0214 収束の判定を既存 gates に載せる

## 何が問題か
収束の判定（`r_hat` / `ess` / divergences）が無いと、発散したサンプリングの結果が正常に見える
（黙って間違う側の欠陥）。一方で判定の形はどれも「指標 × 閾値 × 向き」なので、
**新しい gate kind は要らない**（新 kind を足すと `value_threshold` の二重化になる）。

## やること
- `BAYES_DIAGNOSTICS: Registry[MetricEntry]`：InferenceData → 診断値を計算する住人
  （`r_hat`＝小さいほど良い・`ess_bulk`／`ess_tail`＝大きいほど良い・`divergences`＝小さいほど良い）。
  計算は arviz を使う（再発明しない）。向き（`higher_is_better`）は `MetricEntry` の先例どおり
  `register(entry_cls=MetricEntry, higher_is_better=…)` で持たせる。
- 診断値の dict と向きの表を `GateContext(candidate=…, directions=…)` に詰め、
  `gates.evaluate(ctx, [{"kind": "value_threshold", "metric": "r_hat", "limit": 1.01}, …])` を呼ぶ配線を書く。
  `gates.py` の fail closed（有限性・未測定は不合格）はそのまま働く。

## やらないこと
- `GATES` への新 kind の登録（`value_threshold` で書ける。これが本タスクの中心の制約）。
- 閾値の既定値をコードに焼かない（閾値は config の宣言。「正しい」の定義は人が置く）。

## 受け入れ基準
- 合成 InferenceData の構成から導く：同一のチェーンを複製した合成では `r_hat` が 1 近傍で合格し、
  平均を大きくずらしたチェーンを混ぜた合成では `r_hat > 1.01` で不合格になる。
- `divergences` は `sample_stats.diverging` に仕込んだ True の個数と一致する（構成から導出）。
- 診断値が NaN のとき `value_threshold` が `not_finite` で不合格にする（gates 既存の性質が働く証拠）。
- `sorted(GATES)` がこのタスクの前後で変わらない（別の立場が 1 コマンドで確かめられる）。
- `uv run verify` 全成功。
