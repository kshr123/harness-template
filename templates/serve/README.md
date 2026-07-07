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

## リリース戦略：Blue-Green（image tag 切替＝即ロールバック）

model-in-image は「イメージ＝配る版」なので、リリースは `k8s/deployment.yaml` の `image:` の tag を
旧→新に書き替えるだけ。新しい部品は要らない（このテンプレートが既に持っている物の運用手順）。

1. 新しい champion を焼き込んだイメージを、**版が判る tag** で作って registry に push する。tag に
   `promote_model`（`src/harness/ds/models.py`）が昇格したモデル版を含めると、イメージ⇔champion
   履歴（昇格記録の previous）の対応＝来歴が残る：
   `docker build -f Dockerfile.serve --target model-in-image -t harness-serve:model-in-image-v0002 .`
2. `k8s/deployment.yaml` の `image:` を新しい tag に書き替えて `kubectl apply -f k8s/deployment.yaml`。
   K8s のローリング更新は readinessProbe（`/health`）に通った新 Pod（Green）へだけ切り替える
   （Green が healthy になるまで旧 Pod（Blue）が受け続ける＝停止時間なし）。
3. **ロールバック**＝`image:` を旧 tag に戻して同じ apply をするだけ。旧イメージは registry に
   残っているので再ビルド不要・即時。どの tag がどのモデル版かは手順 1 の tag 規約と
   `promote_model` の昇格記録で追える。

## リリース戦略：Canary（replicas 比率の段階リリース）

`k8s/service.yaml` の `selector:` は **Pod のラベルだけ**を見るので、同じラベル
（`app: harness-serve`）の Pod を持つ Deployment を 2 つ並べれば、Service はおおよそ Pod 数の比率で
両方へ流す。テンプレートの `k8s/deployment.yaml` のコピーだけで実現できる。

1. `k8s/deployment.yaml` をコピーして canary 用 Deployment を作り、次の 3 点だけ替える：
   - `metadata` の `name:` を別名（例 harness-serve-canary）にする（Deployment 名の衝突を避ける）。
   - `matchLabels:` と Pod テンプレート側 `labels:` に区別用ラベル（例 track: canary）を**追加**する。
     `app: harness-serve` は両方に残す（Service の `selector:` に載せ続けるため）。旧側にも同様に
     track: stable を足す（Deployment の selector は不変フィールドなので旧側は作り直しになる点に注意）。
   - `image:` を新しい tag（Blue-Green 手順 1 の tag）にする。
2. 新旧の `replicas:` の比率で流量を決める（例 旧 9 : 新 1 ≒ 新へ約 1 割）。問題が無ければ新側を
   増やし旧側を減らす→最後は正の Deployment の `image:` を新 tag にして（Blue-Green の手順 2）
   canary 側を削除する。
3. **ロールバック**＝canary 側の `replicas:` を 0 にする（または canary の Deployment を削除する）。
   正の Deployment は無傷なので即時に全量が旧版へ戻る。

境界：ここでやるのは **Pod 数の比率**による近似の段階リリースまで。実トラフィックの出し分け
（ヘッダ・ユーザー単位のルーティング）や外部指標収集を伴う A/B テストは配信基盤（service mesh 等）の
関心＝このテンプレートではやらない（`docs/ops.md` の「やらないこと」参照）。
