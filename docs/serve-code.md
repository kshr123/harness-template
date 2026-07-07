# serve のコード — どのファイルが何を担い、どう組まれているか

`docs/serve.md`（配信の使い方と予測ログの契約）の姉妹。こちらは**中身の設計**を説明する：`src/harness/serve/`
の各ファイルが何を担うか、内容がどこにどう書かれているかを、コードを読む前につかめるようにする。読み手は、
配信の仕組みを理解したい・広げたいエンジニア（と、それを助けるエージェント）。この文書が実装と食い違わない
ことは `code_doc_lint`（`uv run verify`）が保証する＝モジュールを足したのにここで触れていないと検査が落ちる。

## 設計の芯

1. **配信は「読むだけ」**。registry（保存済みの版の登録簿）から現 champion を解決して FastAPI で出す。学習も
   保存もしない＝ds が作ったものを配るだけ（起動時に champion を読み込み、無ければ明示エラーで止まる）。
2. **予測は来歴つき JSONL に記録する**。1 予測行の形（`PREDICTION_LOG_FIELDS`）が唯一の契約で、後段の監視
   （`data monitor`）はこれだけに依存する。キーの増減＝契約変更＝この定数・docs/serve.md の表・消費側を同時に直す。
3. **応答スキーマは不変**。新版の下見（shadow 配信）は env で有効化し、応答は常に primary のみ・shadow は
   JSONL に `role: "shadow"` 行を足すだけ（後方互換のキー追加）。
4. **実行基盤は利用者環境の関心**。トラフィック分割・スケール・耐障害には踏み込まず、壊れない**テンプレート**
   （`templates/serve/`）の提供までにする。その腐りは `deploy_lint` が構造検査で止める。
5. **中核とプロファイルの境界**。中核（`src/harness/`）は serve を知らない。serve は config
   （`profiles=[..., "harness.serve"]`）経由でだけ現れる。fastapi/uvicorn はプロファイル経路の外では import しない
   （軽 import）。

## 全体像（流れとファイルの関係）

起動から予測まで一直線：`cli.py` が起動し、`app.py`（FastAPI）が入口、実処理は `runtime.py`（champion 解決・
予測・予測ログ）に集約する。`deploy_lint.py` は実行経路の外＝配布テンプレートの腐り止め。

```text
  cli.py            app.py                     runtime.py
  (uvicorn 起動) ─▶ (FastAPI の入口:      ─▶   champion 解決・予測・
                    /predict /health           予測ログ JSONL
                    /metadata・shadow 分岐)     （PREDICTION_LOG_FIELDS）

  実行経路の外: deploy_lint.py（templates/serve/ の構造 lint）・profile.py（verify 結線）
```

## どのコードがどんな役割か

- `runtime.py` … 配信の実行時部品：champion の解決・予測・来歴つき JSONL 予測ログ（`PREDICTION_LOG_FIELDS`・
  予測ログの中核）。app と cli が共通で使う純粋な部品。
- `app.py` … FastAPI アプリ本体（`/predict`・`/health`・`/metadata`。shadow 配信の 1 プロセス内分岐もここ）。
- `cli.py` … `uv run serve` の入口（uvicorn 起動。fastapi/uvicorn が無ければ導入案内して終了）。
- `deploy_lint.py` … 配信テンプレート（`templates/serve/`）の構造 lint。参照整合を verify で守る（実行しない資産の腐り止め）。
- `profile.py` … serve プロファイルの宣言（`deploy_lint` を verify に載せる）。中核はこれを config 経由でだけ知る。

## どこに・何が・どう書かれているか（内容の在り処）

| 内容 | どこに | それを扱うコード |
| --- | --- | --- |
| 予測ログ 1 行の形（契約） | `PREDICTION_LOG_FIELDS`（`runtime.py`）＋ docs/serve.md の表 | `runtime.py`（書き出し）・`data monitor`（読み） |
| 何を配信するか（版の選択） | 起動引数（`--work`/`--name`/`--version`） | `runtime.py`（champion 解決） |
| shadow（新版の下見）の有効化 | 環境変数 `SERVE_SHADOW_*` | `app.py`（分岐） |
| コンテナ・K8s の配り方 | `templates/serve/`（雛形） | `deploy_lint.py`（構造検査） |

## 拡張の継ぎ目

serve は ds のような「部品レジストリ」を持たない（固定の FastAPI サーバ）。広げるときの継ぎ目は次のとおり：

- **予測ログにキーを足す** … `PREDICTION_LOG_FIELDS`（`runtime.py`）・docs/serve.md の表・監視の消費側を**同時に**直す。
- **新版の下見（shadow / canary）** … env（`SERVE_SHADOW_*`）で分岐（新 CLI は足さない）。応答スキーマは変えない。
- **可搬な保存形式** … serve は ds の保存形式（`FORMATS`）をそのまま読む＝形式追加は ds 側（`docs/ds-code.md`）。
- **配布のテンプレート** … `templates/serve/` に足し、`deploy_lint` の構造検査に載せる。
