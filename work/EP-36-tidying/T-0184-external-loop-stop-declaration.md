---
id: T-0184
kind: task
status: done
title: 定期実行する workflow に停止条件の宣言を必須にする（ci_lint と schedule_lint の非対称を消す）
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_ci_lint.py::test_scheduled_workflow_without_stop_flagged
  - tests/test_ci_lint.py::test_repo_github_workflow_scheduled_without_stop_flagged
  - tests/test_ci_lint.py::test_non_scheduled_workflow_not_required_to_stop
  - tests/test_ci_lint.py::test_stop_marker_format_shared_with_schedule_lint
---
## 実装（done）
- 書式の正本を core に 1 か所置いた：`pm.STOP_DECLARATION_RE` / `pm.has_stop_declaration`（schedule_lint と
  ci_lint が同じ判定を読む＝2 つ目の書式を作らない）。schedule_lint の `_check_stop_comment` もこれを読むよう置換。
- `ci_lint._check_schedule_stop`：`.github/workflows/**` と `templates/ci/**` の workflow のうち on.schedule を
  持つものに `# stop:` を要求（`templates/ci/` の有無に依らず走る＝自前の scheduled workflow も検査）。
- `retrain.yml` に `# stop:` を追加して緑に戻した（実測で赤→緑を確認）。

# T-0184 止め方を宣言していない外部ループを verify で止める

## 何が問題か
`src/harness/agent/schedule_lint.py` は、定期実行の workflow に停止条件の宣言（`# stop:`）が無いと
error にする。ところが `src/harness/ops/ci_lint.py` は `templates/ci/.github/workflows/retrain.yml` に
同じ要求をしていない。実測：`monitor.yml` には `# stop:` があり、`retrain.yml` には **0 件**。

同じ「止め方の無いループ」が、片方だけ検査されている。継続学習は放置すると回り続ける側なので、
検査が無い方が危ない。

## なぜ検査してよいのか（L-017 との関係）
L-017 は「自分が作りうる欠陥に検出器を足すな。発生源を塞げ」と言う。これは検出器ではない。

ループの**発生源が機械的に列挙できる**からである。定期実行の workflow は `on.schedule` を持つ、
という構文上の印を必ず持つ。「`on.schedule` を持つ workflow は停止条件の宣言が要る」は、
`Registry(require_source=True)` と同じ形の fail closed である（書き忘れを不可能にする。
中身の真偽までは機械には分からない、と正直に申告する点も同じ）。

逆に、プロセス内の反復（`TUNERS` の optuna 試行・`k_scan`・変種の反復）に同じ検査は作れない。
そこにはループの印が無く、台帳に自己申告させるしかないからである。自己申告の台帳は
「申告し忘れた第 1 号を必ず通す」ので、まさに L-017 が禁じた検出器になる。**だから作らない。**

なお、プロセス内の反復は `k_values: Sequence[int] = range(2, 11)` や `n_trials` のように
**構造的に停止する**。止め方の宣言が要るのは、外から起動されて自分では止まらないループだけである。

（この判断は、`src/harness/loops.py` と `Profile.loops` 台帳を新設する案を独立レビューが退けた結果。
その案は「入口の無いカタログは嘘の入口になる」という自分自身の論拠と矛盾していた。）

## 何をするか
- `ci_lint` が `.github/workflows/**` と `templates/ci/**` の workflow を読み、`on.schedule` を持つものに
  停止条件の宣言を要求する。宣言の書式は `schedule_lint` の `# stop:` に揃える（2 つ目の書式を作らない）。
- 検査を足すと `retrain.yml` が赤くなる。同じタスクで `retrain.yml` に停止条件を書いて緑に戻す。

## 受け入れ基準
- `on.schedule` を持ち `# stop:` の無い workflow を置くと `uv run verify` が失敗する（実測。仕込んだら戻す）。
- `on.schedule` を持たない workflow（`ci.yaml` 等）は要求されない。
- 停止条件の書式は `schedule_lint` と同一（両方が読む定数を 1 か所に置く）。
- `uv run verify` 全成功。

## やらないこと
- `src/harness/loops.py`（`Trigger` / `Stop` / `InProcessLoop | ExternalLoop`）を作らない。実 import する
  消費者がこの検査しかいない＝自己正当化になる。型の置き場は必要になってから作る。
- `Profile.loops` 台帳を作らない（自己申告制＝検出器）。
- `TRIGGERS` / `STOP_CONDITIONS` / `POLICIES` をレジストリにしない（名前 → 工場の解決点が無い）。
