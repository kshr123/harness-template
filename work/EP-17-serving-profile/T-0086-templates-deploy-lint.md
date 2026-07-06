---
id: T-0086
kind: task
status: done
title: 配信テンプレート（Dockerfile/compose/k8s）＋deploy_lint を PROFILE に配線＋doclint templates/
created: 2026-07-06
closed: 2026-07-06
verified_by: [tests/test_serve_deploy_lint.py]
depends_on: [T-0085]
---
# T-0086 配信テンプレート＋deploy_lint

## 背景（DEC-0013・release patterns の翻案）
Docker/K8s/FastAPI 資産を「利用者がコピーする雛形」として同梱し、実行はせず**構造 lint**で参照整合を verify で守る
（DEC-0009 の「入口＝lint＋スキル」・E-0001 を e2e が叩くのと同じ「腐らせない」思想の、実行できない資産版）。

## 受け入れ基準
- `templates/serve/`：
  - `README.md`（コピー手順・model-in-image と model-load の選択基準・`uv sync --extra ds --extra serve --extra onnx`）。
  - `Dockerfile.serve`（python:3.14-slim＋uv・**マルチターゲット** model-load / model-in-image・EXPOSE 8000・ENTRYPOINT で `uv run serve --host 0.0.0.0 --port 8000` を env SERVE_WORK/SERVE_NAME 経由・`uv sync --frozen --extra ds --extra serve --extra onnx`）。
  - `docker-compose.serve.yml`（2 サービス＝in-image / model-load[volume ./data:ro]・healthcheck /health）。
  - `k8s/{namespace,deployment,service}.yaml`（deployment=model-in-image・readinessProbe /health・env SERVE_WORK/SERVE_NAME・service port 8000）。
- **`src/harness/serve/deploy_lint.py`**：`run_checks(root)->list[pm.Problem]`（PmCheck 型）。Docker build/kubectl は実行しない・stdlib＋pyyaml のみ（serve extra 無しでも verify で走る）。`templates/serve/` が無ければ空（コピー先で誤検知しない）。検査＝参照整合：必須ファイル存在／port 一貫（EXPOSE＝ENTRYPOINT --port＝compose ports＝containerPort＝targetPort）／image 名一貫（compose＝deployment）／namespace 一貫／selector 整合／`uv sync` に `--extra serve`／env SERVE_WORK/SERVE_NAME の三者一致。指摘は「どのファイルのどの値 vs どの値」を名指し。
- **配線**：`serve/profile.py` の pm_checks に `deploy_lint.run_checks` を追加（checks.py は不変＝profiles 経由で自動合流）。`.harness/config.toml` の profiles を `["harness.ds", "harness.serve"]` に（deploy_lint が自リポの出荷テンプレを毎回検査）。
- **doclint**：`src/harness/doclint.py` の `_PATH_RE` に `templates/` 接頭辞を追加（`templates/serve/...` 参照の死にリンク検査＝新盲点）。

## 触ってよいファイル
`templates/serve/**`（新規）・`src/harness/serve/deploy_lint.py`（新規）・`src/harness/serve/profile.py`（pm_checks 追加）・
`src/harness/doclint.py`（_PATH_RE）・`.harness/config.toml`（profiles）＋`tests/test_serve_deploy_lint.py`・`tests/test_doclint*.py`（実在名）。

## 検査（テスト先書き・構成から導く）
- 壊し fixture（port 不一致・image 不一致・extra 欠落・selector 不整合…）で各検査が error・実テンプレート（自リポ）は 0 件で通る（integration）。
- profiles 経由で `uv run check` の出力に serve の検査が合流。doclint が `templates/` の死にリンクを検出。
- `uv run verify` 全体緑（自リポ config に harness.serve を足しても軽 import で PM 検査が回る）。

## 独立レビュー（maker≠checker・差分のみ・実測）
別セッションの独立レビュアーが commit `08679d1` の差分だけを実測。指摘 0 件（クリーン）：
実装側変異（port/env/selector/namespace/image/--extra serve の各検査を無効化）はすべて対応テストが
RED＝mutant killed／偽陽性なし（自リポ実テンプレは `run_checks(REPO_ROOT)==[]`）／コピー先で第 2 サービスの
ポートだけ壊しても検知（全サービス走査）／軽 import 境界（fastapi/uvicorn/polars 非ロード）を subprocess で
確認／doclint の `templates/` 追加で既存パス検出・死にリンク判定に回帰なし（doclint 14 件緑）／指摘メッセージが
「どのファイルのどの値 vs どの値」を含むことを確認。
