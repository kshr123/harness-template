---
id: T-0217
kind: task
status: todo
title: PSIS-LOO によるモデル比較と採用（harness.promotion の作法に載せる）
created: 2026-07-11
depends_on: [T-0215, T-0216, T-0173, T-0174, T-0175]
verified_by: []
---
# T-0217 比較と採用（背骨の最後の 2 段）

## 何が問題か
ベイズモデル同士を比べる正本（PSIS-LOO）と、比べた結果を採用する経路が無い。採用の記録・champion の
解決・切り戻しは EP-33 が `harness/promotion.py` に一本化する（T-0173〜T-0175）ので、stats 専用の
採用機構を発明してはいけない（複製が 3 つ目になる）。

## やること
- arviz の `loo`／`compare` で PSIS-LOO 比較を出す（再発明しない）。比較できるのは
  **同じ観測に対するベイズモデル同士だけ**——docstring と `docs/stats.md` にこの限界を正直に書く
  （ds の champion（GBM 等）とはこの経路では比べられない。跨ぐ比較が実際に要ると分かった時点で
  データ層の橋を検討する、まで書く）。
- 採用は `harness.promotion` の作法（判定は `GATES`＋T-0214 の directions・記録は promotions/ の形式）に
  載せる。方針（どの診断・どの閾値）は呼び手＝config が持つ（promotion は policy-free の規約）。
- Pareto k の警告（PSIS-LOO の信頼性診断）を黙殺しない：k が悪い比較は結果に事実として残す。

## やらないこと
- MCMC から ds `MODELS` へのブリッジ（事後を点推定に潰す。エピックの「作らないもの」）。
- ds の leaderboard への相乗り（共有しない側の部品。台帳の**形式**だけ共有する）。
- 人手承認フロー（`pending_manual_approval`）の実装（語彙は promotion 側の将来拡張）。

## 受け入れ基準
- 合成データの構成から導く：データを生成した真のモデルと、わざと誤指定したモデルを同一データで
  比較したとき、elpd の順位が真のモデル優位になる。
- 採用の記録が promotions/ の形式で残り、`rollback`（T-0175 の操作）で前の版に戻せる。
- 収束判定（T-0214）に落ちた版は採用経路で `rejected` になる（gates の fail closed が採用まで届く証拠）。
- `uv run verify` 全成功。
