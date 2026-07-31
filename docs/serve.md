# serve — 学習済みモデルの配信（FastAPI）と予測ログの契約

- **読者**：人（エンジニア）
- **種別**：reference（配信と予測ログの契約）
- **分かること**：champion を予測 API として配信する仕組みと、予測ログの契約
- **ここからやること**：`uv run serve --help` で配信を使い始める

学習済みモデルの現在の採用版（champion）を FastAPI の予測 API として配信し、
すべての予測を由来つき（その予測がどの版のモデル・どの入力から出たかを後から辿れる情報つき）の
JSONL（1 行に 1 件の JSON を並べたテキスト形式。prediction log＝予測ログ）へ記録する
プロファイル。配れるのは registry（保存済みの版の登録簿）で
採用（評価の合否判定を通って champion になること）済みの版だけ。
モデルを配信する人と、予測 API の契約（エンドポイント・ログの行形式）を確かめたい人が読む Reference。

実装は `src/harness/serve/`（どのファイルが何を担い・どう組まれ・今後どう広がるかは `docs/serve-code.md`）。
予測ログは MLOps の prediction log パターンの翻案。作業手順の案内は `.claude/skills/serve/SKILL.md`。

## 使い方（How-to）

```
uv sync --extra ds --extra serve
uv run serve --work E-0001 --name baseline [--version <版>] [--host 127.0.0.1] [--port 8000] [--log-dir <置き場>]
```

- 起動時に champion を読み込む。champion が無い（採用していない）と明示エラーで止まる。
  `--version` で版を明示すれば採用前の版も出せる（緊急・検証用）。
- fastapi/uvicorn が無い環境では導入方法を案内して exit 1。

## エンドポイント（契約）

- `GET /health` … `{"status": "ok", "model": {"work", "name", "version"}}`（何が載っているかまで返す）。
  version 指定なし（現 champion 配信）で起動した場合は、毎回ディスクの昇格記録と載っている版を突き合わせる：
  切り戻し・再昇格の後に載っている版が現 champion と食い違えば `status: "stale"`・`champion`（現 champion の版）
  つきで **HTTP 503** を返す。503 で k8s の readinessProbe / compose の healthcheck がその配信を自動で外す
  ＝切り戻しが「人が再起動を覚えている」でなく機構で配信の実体まで届く。version を明示して起動した場合
  （運用が意図して版を固定）は突合しない（固定は意図した状態なので champion との食い違いを異常と見なさない）。
- `GET /metadata` … モデル manifest（保存物に付く由来書き＝版・作成元データ・形式などのメタデータ 1 枚）の構造化（work/name/version/format/fingerprint/data_fingerprint/
  feature_names/metrics/python/dependencies/created）＋ `prediction_kind`。
- `POST /predict` … 本文 `{"records": [{列名: 値}, ...]}`（全行同じ列）。応答は
  `{"predictions", "prediction_kind", "model", "request_id", "n"}`。predictions の形は prediction_kind に応じる：
  - `proba`（二値分類）＝陽性（ラベル 1）の確率の一覧（float）。
  - `multiclass_proba`（多クラス）＝行ごとにクラス 0..k-1 の確率の一覧（list[float]。陽性 1 列に潰さない）。
  - `value`（回帰）＝予測値の一覧（float）。
- 空の records・行ごとの列の食い違い・列不足や型不一致で予測できない入力は **422**（黙って 200 にしない）。

## 予測 JSONL の行スキーマ（契約）

予測は成功するたびに JSONL へ追記される。置き場は既定
`artifacts/serve/predictions/<モデル名>/<YYYYMMDD>.jsonl`（UTC の日付で 1 ファイル・`--log-dir` で変更可）。
**1 行＝1 予測行**。キーと型（正本はコードの定数 `PREDICTION_LOG_FIELDS`＝`src/harness/serve/runtime.py`）：

| キー | 型 | 意味 |
| --- | --- | --- |
| `time` | str | ISO 8601・UTC。同じリクエストの行は同じ値 |
| `request_id` | str | uuid4 hex。同じリクエストの行は同じ値 |
| `row` | int | リクエスト内の行番号（0 始まり） |
| `model` | dict | `work`・`name`・`version`・`fingerprint`（str。中身から計算した短い識別子で、どのモデル実体かを一意に示す。manifest と同じ値） |
| `prediction_kind` | str | `proba` \| `multiclass_proba` \| `value` |
| `input_fingerprint` | str | features の正準 JSON（キー昇順・区切り最小）の sha256。`runtime.input_fingerprint(features)` で再計算できる |
| `features` | dict | 列名→入力値（受信した record そのまま） |
| `prediction` | float \| list[float] | proba/value は float・multiclass_proba はクラス 0..k-1 の確率の list[float] |
| `role` | str | `primary`（応答を返した champion）\| `shadow`（並走した shadow 版）。**常に付与**（shadow 未設定でも `primary`）＝読み手は有無で場合分けしない |

この契約は後続の監視（`data monitor`）が唯一依存するもの。キーの増減・改名は契約の変更＝
`PREDICTION_LOG_FIELDS`・この表・消費側を同時に直すこと。

## shadow 配信（1 プロセス内分岐・env で明示有効化）

shadow deployment（シャドー配信）＝本番のリクエストを新版にも並走させ、
応答は返さずログだけ残す運用。champion（primary）の応答は変えずに、**同じ入力**を shadow 版でも予測して
同じ JSONL に `role: "shadow"` の行を残す。実行時基盤（トラフィック分割・サイドカー）には踏み込まない
（運用上の位置づけは `docs/ops.md` の shadow 節）。

```
SERVE_SHADOW_NAME=challenger uv run serve --work E-0001 --name baseline
```

- **有効化は env のみ**（新 CLI オプションは無い）：`SERVE_SHADOW_NAME`（shadow のモデル名。未設定・空なら
  完全に従来どおり）・`SERVE_SHADOW_WORK`（既定＝primary と同じ work）・`SERVE_SHADOW_VERSION`
  （既定＝shadow 名の現 champion）。
- shadow も**起動時に読み込む**（無ければ明示エラー＝設定ミスをリクエスト時まで持ち越さない）。
- `/predict` の**HTTP 応答は常に primary のみ**（応答スキーマ不変）。JSONL には 1 予測行につき
  primary＋shadow の 2 行が同じ `request_id`・同じ `input_fingerprint` で並ぶ（monitor の突き合わせ用）。
  shadow 行の `model`・`prediction_kind`・`prediction` は shadow 版のもの。
- **shadow の予測失敗は応答を落とさない**：primary は 200 で返し、shadow 行は**書かない**（エラー値で
  契約の `prediction` 型を汚さない）。失敗は警告ログ（logging）にだけ残る。
- `/metadata` は shadow 有効時のみ `shadow`（work/name/version）キーを足す（後方互換のキー追加のみ）。
- **監視での注意**：shadow を有効にすると、同じ入力が primary＋shadow の 2 行になる。
  - 無区別に数えると `n_served` が二重計上になり、要約が両 role の混合になる。
  - `data monitor` は **`--role`（primary | shadow | all）**で行を絞る。既定は `primary`＝shadow 行を
    除外した、shadow 無しのときと同じ集計。
  - shadow 版だけの分布を見るなら `--role shadow`。全行（突き合わせ・件数確認）は `--role all`。
  - `role` キーが無い旧ログ行は primary 扱い（後方互換）。

## loops との関係（serve は loop でない）

serve はリクエスト駆動（`/predict`・`/invoke` とも 1 呼び 1 応答のレイテンシ契約）で、「停止条件が満たされる
まで作業サイクルを繰り返す」loopsには該当しない。応答経路に評価器ゲートを
挟むのは配信の関心（レイテンシ・可用性）と衝突するため、意図的に適用しない（適用しない、という判断自体が
正本）。serve を回す loop は serve の外側にある：予測 JSONL→`data monitor`（→`--file-issue`）→
retrain という ops の周回（`docs/ops.md`）。

## コンテナ・K8s で配るとき

`templates/serve/` の雛形（Dockerfile/compose/k8s）をコピーして案件側で調整する。
実行基盤（ルーティング・スケール・耐障害）は利用者環境の関心＝当リポは壊れないテンプレートの提供まで。
可搬な保存形式（ONNX）は extra `onnx`（`uv sync --extra ds --extra onnx`）。
