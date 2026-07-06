---
id: T-0085
kind: task
status: done
title: serving プロファイル（FastAPI app・serve CLI・予測 JSONL ログ・PROFILE・serve スキル）
created: 2026-07-06
closed: 2026-07-06
verified_by: [tests/test_serve_app.py, tests/test_serve_cli.py]
depends_on: [T-0048]
---
# T-0085 serving プロファイル（harness.serve）

## 背景（DEC-0013・sync 配信＝web_single_pattern の翻案）
champion を FastAPI で出す。中核・ds を壊さず新パッケージ `src/harness/serve/` に閉じる。extra `serve`・script `serve` は導入済み。

## 受け入れ基準（プロファイル境界・DEC-0004/0009・軽 import）
- 新パッケージ `src/harness/serve/`：
  - `__init__.py`＝`from harness.serve.profile import PROFILE` の再 export のみ（ds/__init__ と同型）。
  - `profile.py`＝`PROFILE = Profile(name="serve", pm_checks=())`（T-0086 が deploy_lint を足す）。harness.profiles と stdlib のみ import。
  - `runtime.py`＝champion 解決＋load_model＋prediction_kind 判定＋`predict_frame`（cli.py の cv._predict 分岐を関数化）＋JSONL 予測ログ（スキーマ定数・追記・入力指紋）。polars/numpy は関数内遅延 import。
  - `app.py`＝`create_app(root, *, work, name, version=None, log_dir=None) -> FastAPI`。起動時に champion（無ければ明示エラー）を load して app.state に。`GET /health`（status＋model 版）・`GET /metadata`（ModelRecord の構造化＋prediction_kind/feature_names）・`POST /predict`（`{"records":[{列名:値}...]}`→prediction_kind に応じ predictions＋model＋request_id）。列不足・空 records は 422（黙って 200 にしない）。fastapi は app.py の module top で import 可（この経路は profile から辿られない）。
  - `cli.py`＝typer `serve_main`（`--work --name [--version] [--host 127.0.0.1] [--port 8000] [--log-dir] [--root]`→create_app→uvicorn.run）。fastapi/uvicorn 未導入は案内して exit 1。
- **予測 JSONL ログ**（prediction_log 翻案）：既定 `artifacts/serve/predictions/<name>/<YYYYMMDD>.jsonl`。1 行＝1 予測行（time・request_id・row・model{work,name,version,fingerprint}・prediction_kind・input_fingerprint・features・prediction）。この行スキーマ（キー・型）を runtime.py の定数＋`docs/serve.md` に契約として明記（T-0087 monitor はこの契約だけに依存）。
- **入口**（DEC-0009）：`.claude/skills/serve/SKILL.md`（新設・新しい作業種別＝配信のフェーズスキル。手順＝champion を確認→`uv run serve`→`templates/serve` をコピー→`data formats`/onnx への導線）。散文の使い方ガイドは作らない。

## 触ってよいファイル
`src/harness/serve/{__init__,profile,runtime,app,cli}.py`（新規）・`docs/serve.md`（新規）・`.claude/skills/serve/SKILL.md`（新規）＋
`tests/test_serve_app.py`・`tests/test_serve_cli.py`（新規）。`.harness/config.toml` は T-0086 で（deploy_lint と同時に profiles 追加）。他は読み取りのみ。

## 検査（テスト先書き・TestClient・ネットワーク無し・fastapi は importorskip）
- conftest の一時プロジェクトに小 Pipeline を save_model→promote→create_app→TestClient：/health 200・/metadata が record と一致・/predict の値が同じ df への cv._predict 直呼びと allclose（写経でなく性質）・多クラス/回帰の応答形・列不足 422・champion 不在で起動失敗・JSONL の行数/キー/input_fingerprint 再計算一致。
- serve CLI：uvicorn.run を monkeypatch し引数（host/port と app）・fastapi 不在時の案内を検査。実 uvicorn は起動しない。
- **軽 import テスト**：subprocess で `import harness.serve` 後に `"fastapi" not in sys.modules` を assert。

## 独立レビュー（maker≠checker・差分のみ・実測）
別セッションの独立レビュアーが commit `f9255ec` の差分を実測（TestClient で /health・/metadata 一致・
/predict が cv._predict 直呼びと allclose・多クラス/回帰の応答形・列不足 422・champion 不在で起動失敗・
JSONL の行数/キー/input_fingerprint 再計算一致・serve CLI の uvicorn.run 引数・軽 import 境界）。
指摘＝input_fingerprint に既知値アンカーが無い→既知の features での sha256 固定値テストを追加（commit `4b17af5`）。反映後クリーン。
