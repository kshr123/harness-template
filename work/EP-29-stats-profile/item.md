---
id: EP-29
kind: epic
status: todo
plan: detailed
requirements: [REQ-001]
depends_on: [EP-27, EP-33]
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

## Python 3.14 に載るか（2026-07-10 実測・2026-07-11 に再測定）
nutpie 0.16.11 に cp314 wheel あり。pytensor 3.1.2 も cp314 あり（`>=3.12,<3.15`）。pymc 6.1.0 と
arviz 1.2.0 は pure-python。`uv pip install --dry-run pymc nutpie arviz` は 3.14 venv で解決に成功
（2026-07-11・PyPI JSON 直読＋uv の解決で確認）。**スタックは 3.14 に載る**ので、EP-29 は
T-0188（環境の軸）に依存しない。ただし netCDF 保存ライブラリ（netcdf4／h5netcdf）の 3.14 可否は
**未確認**（T-0211 で実測して確定する）。依存の可否は日付つきの事実なので、各タスク着手時に再測定する。

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

## タスク（2026-07-11 分解・1 タスク＝1 コミット）
| ID | 何を | 順 | 依存 |
| --- | --- | --- | --- |
| T-0211 | stats extra（pymc・nutpie・arviz＋netCDF 保存ライブラリ）を pyproject に足し 3.14 で実測確定 | 1 | — |
| T-0212 | `harness/stats` プロファイルの器（profile.py・docs/stats.md・test glob・config 並記） | 2 | T-0211 |
| T-0213 | `BAYES_MODELS`＋`SAMPLERS`（nutpie 既定・PyMC フォールバック）で推論を一巡（walking skeleton・`--test` を verify へ） | 3 | T-0212 |
| T-0214 | `BAYES_DIAGNOSTICS`＋既存 `value_threshold` で収束判定（新 gate kind なし） | 4 | T-0213 |
| T-0215 | InferenceData の保存・読込（netCDF・manifest の format 分岐・fingerprint） | 5 | T-0213 |
| T-0216 | 事前・事後予測検査（`PPC_CHECKS`・指標×閾値×向きの形に落とす） | 6 | T-0214 |
| T-0217 | PSIS-LOO 比較と採用（`harness.promotion` の作法。プロファイル跨ぎ比較不可の代償を明記） | 7 | T-0215, T-0216, T-0173〜T-0175 |
| T-0218 | stats CLI（カタログ）と docs 導線（coverage_lint に載せる） | 8 | T-0217 |

**着手順の拘束**：エピックとしての着手は EP-33 の T-0173〜T-0175（昇格の中核一本化・alias・rollback）の後。
採用の経路（T-0217）が `harness.promotion` に依存するためで、先に stats 専用の採用機構を書くと
複製が 3 つ目になる。T-0214 と T-0215 は並行できる（T-0213 の後）。

## L-017 の適用記録（機構を足す前の自問：発生源の封鎖か、単なる検出器か）
- **収束判定の新 gate kind（`convergence` 等）→ 却下**。判定はどれも「指標 × 閾値 × 向き」で、既存の
  `value_threshold` の spec で書ける（`gates.py` を読んで確認済み。向きは `GateContext.directions` に
  呼び手が渡す設計で、stats は `BAYES_DIAGNOSTICS` の `higher_is_better` から渡せる）。新 kind は機構の
  二重化であって、封鎖でも検出でもない。
- **MCMC の実行時間の計測・テレメトリ → 却下**。遅い verify を防ぐのは「極小モデル・少 draw の
  `--test` を雛形の規約にする」（発生源側）で足りる。実行時間の計測は既に遅くなった後にしか鳴らない検出器で、
  消費者も居ない。
- **「診断の閾値を書き忘れたら失敗」の専用検査 → 却下（不要）**。gates は「測っていない指標は不合格
  （`not_measured`）」を既に持つ（fail closed）。書き忘れは既存機構が止めるので、新しい検査を作らない。
