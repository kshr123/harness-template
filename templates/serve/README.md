# templates/serve — 配信テンプレート（Docker / compose / K8s）

学習済みの champion を FastAPI（`uv run serve`）でコンテナ配信するための雛形。
**実行しない資産**なので、ファイル間の参照整合（port・image・namespace・selector・extra・env）は
deploy_lint（`src/harness/serve/deploy_lint.py`）が `uv run verify` のたびに構造検査して腐りを止める。

## 構成

| ファイル | 役割 |
|---|---|
| `Dockerfile.serve` | 配信イメージ。マルチターゲット（`model-load` / `model-in-image`） |
| `docker-compose.serve.yml` | 2 形態それぞれのサービス定義（healthcheck 付き） |
| `k8s/namespace.yaml` | 専用 namespace |
| `k8s/deployment.yaml` | model-in-image イメージの Deployment（readinessProbe /health） |
| `k8s/service.yaml` | ClusterIP Service（port 8000） |

## コピー手順

1. 依存を入れる：`uv sync --extra ds --extra serve --extra onnx`（onnx は可搬な保存形式が要るときだけ）。
2. このフォルダの中身を案件リポジトリの根へコピーする：
   - `Dockerfile.serve`・`docker-compose.serve.yml` → リポジトリの根
   - `k8s/` → リポジトリの根の `k8s/`
3. 配るモデルに合わせて値を替える（deploy_lint が守る整合を崩さないよう対で替える）：
   - env `SERVE_WORK`（作業単位ID）・`SERVE_NAME`（モデル名）＝ compose と `k8s/deployment.yaml` の 2 箇所。
   - イメージ名 `harness-serve:...`（compose と deployment）・namespace `harness-serve`（k8s 3 ファイル）は
     案件名に合わせて一括置換。
4. 起動：
   - compose：`docker compose -f docker-compose.serve.yml up --build serve-model-load`（開発）
     または `serve-in-image`（配布形）。
   - K8s：`docker build -f Dockerfile.serve --target model-in-image -t harness-serve:model-in-image .` で
     イメージを作って registry に push → `kubectl apply -f k8s/`。

## model-in-image と model-load の選び方

| | model-in-image | model-load |
|---|---|---|
| モデルの持ち方 | `data/` をイメージに焼き込む | イメージに入れず、実行時に `./data` を volume で読む |
| 向く場面 | 本番・K8s 配布（イメージ＝配る版。ロールバックはイメージの切り替え） | 手元の開発・頻繁な差し替え（再ビルド不要） |
| 再現性 | 高い（イメージの指紋で版が固定される） | マウント先に依存（差し替え自由の裏返し） |
| イメージサイズ | モデルぶん大きい | 軽い |

判断の軸：**配る先が自分の手元を離れるなら model-in-image**（動く物一式が 1 個で完結する）。
**モデルだけを高速に回して試すなら model-load**（コード・依存の層はそのまま、モデルだけ差し替え）。

## 前提（テンプレートが決め打ちにしている値）

- ポートは **8000** で統一（`EXPOSE`＝`--port`＝compose のコンテナ側＝`containerPort`＝`targetPort`）。
- 配るモデルの指定は env `SERVE_WORK` / `SERVE_NAME`（ENTRYPOINT がこの 2 つを `uv run serve` に渡す）。
- モデルの置き場は `.harness/config.toml` の既定（`file:data`）＝ `data/` 配下。変えている案件は
  `Dockerfile.serve` の COPY と compose の volume を合わせて直すこと。
