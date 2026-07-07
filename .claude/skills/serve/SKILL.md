---
name: serve
description: 学習済みモデル（champion）を配信・サービングする際に自動参照。FastAPI で /predict・/health・/metadata を出し、予測を来歴つき JSONL に記録する。配信・サービング・serve・推論 API・エンドポイント・デプロイ・FastAPI・Docker・K8s の語で発火。
---

# serve（champion の配信＝FastAPI・予測は来歴つき JSONL）

配信は学習の後工程。配るのは registry（保存済みの版の登録簿）の champion（昇格の関門を通った現在の採用版）
だけ。契約（エンドポイント・予測 JSONL の行スキーマ）の正本は docs/serve.md（監視 data monitor はこの契約
だけに依存する）。用語（champion・registry・shadow deployment・role など）の定義は docs/glossary.md。

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
6. 配信後の分布ずれを見張る：`uv run data monitor --baseline <学習基準の表 id> [--auc] [--since YYYY-MM-DD]
   [--role primary|shadow|all] [--file-issue]`（予測 JSONL×学習基準の PSI/band。門番にせず band で読む＝exit 0。
   既定 `--role primary` は shadow 行を除外・`--file-issue` は PSI_ALERT 超で issues に冪等起票＝閉ループは
   docs/ops.md の「監視→課題起票の閉ループ」。ログの正本は docs/serve.md の行スキーマ）。
7. 新版を本番トラフィックで下見するなら shadow deployment（シャドー配信）：`SERVE_SHADOW_NAME=<shadow 名>`
   を付けて起動すると応答は primary のまま、同じ入力の shadow 予測が `role: shadow` で JSONL に並ぶ
   （docs/serve.md の shadow 節）。
8. 実時間 API でなく、保存済みテーブルにまとめて予測したいとき（バッチ推論）は配信せずに
   `uv run data predict --work <ID> --name <モデル名> --table <表 id> [--version <版>]`
   （champion を読み、予測 parquet＋来歴 manifest を書く）。

## してはいけないこと
- 昇格していない版を既定で配らない（champion が正本。--version は緊急・検証用の明示に限る）。
- 予測 JSONL の行スキーマ（docs/serve.md・runtime.PREDICTION_LOG_FIELDS）を勝手に変えない（monitor が依存する契約）。
- 配信コードに前処理を書き足さない（前処理は保存済み Pipeline の中＝学習時と同じものが動く）。
