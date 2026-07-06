---
name: serve
description: 学習済みモデル（champion）を配信・サービングする際に自動参照。FastAPI で /predict・/health・/metadata を出し、予測を来歴つき JSONL に記録する。配信・サービング・serve・推論 API・エンドポイント・デプロイ・FastAPI・Docker・K8s の語で発火。
---

# serve（champion の配信＝FastAPI・予測は来歴つき JSONL）

配信は学習の後工程。配るのは registry の champion（昇格済みの版）だけ。契約（エンドポイント・
JSONL 行スキーマ）の正本は docs/serve.md（監視 data monitor はこの契約だけに依存する）。

## 手順
1. 配る版を確認する：`uv run data saved --work <ID>`（★＝現 champion）。champion が無ければ先に実験→昇格
   （promote_model）。旧版・昇格前の版を出すのは `--version` の明示だけ（緊急・検証用）。
2. 依存を入れる：`uv sync --extra ds --extra serve`。可搬な保存形式（ONNX）が要るなら `--extra onnx` も
   （形式の一覧は `uv run data formats`）。
3. 起動：`uv run serve --work <ID> --name <モデル名> [--version <版>] [--host 127.0.0.1] [--port 8000]`。
   起動時に champion を読み込む（無ければ明示エラー＝黙って空で立たない）。
4. 使う：GET /health（生存＋版）・GET /metadata（来歴）・POST /predict（`{"records":[{列名:値}...]}`・
   不正な入力は 422）。予測は artifacts/serve/predictions/<モデル名>/<YYYYMMDD>.jsonl に 1 行=1 予測で
   追記される（行スキーマは docs/serve.md）。
5. コンテナ・K8s で配るときは `templates/serve/` の雛形をコピーして案件側で調整する（T-0086 で追加。
   実行基盤は利用者環境の関心）。

## してはいけないこと
- 昇格していない版を既定で配らない（champion が正本。--version は緊急・検証用の明示に限る）。
- 予測 JSONL の行スキーマ（docs/serve.md・runtime.PREDICTION_LOG_FIELDS）を勝手に変えない（monitor が依存する契約）。
- 配信コードに前処理を書き足さない（前処理は保存済み Pipeline の中＝学習時と同じものが動く）。
