# serve — champion の配信（FastAPI・sync 配信）と予測 JSONL の契約

学習ハーネスの registry から現 champion（昇格済みの版）を読み込み、FastAPI で予測 API を出す
（DEC-0013・prediction_log パターンの翻案）。実装は `src/harness/serve/`（app.py＝API・runtime.py＝
champion 解決/予測/ログ・cli.py＝uvicorn 起動）。導線は `.claude/skills/serve/SKILL.md`。

## 使い方

```
uv sync --extra ds --extra serve
uv run serve --work E-0001 --name baseline [--version <版>] [--host 127.0.0.1] [--port 8000] [--log-dir <置き場>]
```

- 起動時に champion を読み込む。champion が無い（昇格していない）と明示エラーで止まる
  （`--version` で版を明示すれば昇格前の版も出せる＝緊急・検証用）。
- fastapi/uvicorn が無い環境では導入方法を案内して exit 1。

## エンドポイント

- `GET /health` … `{"status": "ok", "model": {"work", "name", "version"}}`（何が載っているかまで返す）。
- `GET /metadata` … モデル manifest の構造化（work/name/version/format/fingerprint/data_fingerprint/
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
| `model` | dict | `work`・`name`・`version`・`fingerprint`（str。モデル manifest と同じ来歴） |
| `prediction_kind` | str | `proba` \| `multiclass_proba` \| `value` |
| `input_fingerprint` | str | features の正準 JSON（キー昇順・区切り最小）の sha256。`runtime.input_fingerprint(features)` で再計算できる |
| `features` | dict | 列名→入力値（受信した record そのまま） |
| `prediction` | float \| list[float] | proba/value は float・multiclass_proba はクラス 0..k-1 の確率の list[float] |
| `role` | str | `primary`（応答を返した champion）\| `shadow`（並走した shadow 版。T-0113）。**常に付与**（shadow 未設定でも `primary`）＝読み手は有無で場合分けしない |

この契約は後続の監視（`data monitor`・T-0087）が唯一依存するもの。キーの増減・改名は契約の変更＝
`PREDICTION_LOG_FIELDS`・この表・消費側を同時に直すこと。

## shadow 配信（1 プロセス内分岐・env で明示有効化）

champion（primary）の応答は変えずに、**同じ入力**を shadow 版でも予測して同じ JSONL に `role: "shadow"` の
行を残す（本番トラフィックでの新版の下見。実行時基盤＝トラフィック分割・サイドカーには踏み込まない。
位置づけは `docs/ops.md` の shadow 節）。

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
- **監視での注意**：shadow を有効にすると同じ入力が primary＋shadow の 2 行になるため、無区別に数えると
  `n_served` が二重計上になり要約が両 role の混合になる。`data monitor` は **`--role`（primary | shadow |
  all・T-0115）**でこれを絞る：既定 `primary`＝shadow 行を除外した従来（shadow 無し）相当の集計。shadow 版
  だけの分布を見るなら `--role shadow`、全行（突き合わせ・件数確認）は `--role all`。`role` キーが無い
  旧ログ行は primary 扱い（後方互換）。

## コンテナ・K8s で配るとき

`templates/serve/` の雛形（Dockerfile/compose/k8s。T-0086 で追加）をコピーして案件側で調整する。
実行基盤（ルーティング・スケール・耐障害）は利用者環境の関心＝当リポは壊れないテンプレートの提供まで。
可搬な保存形式（ONNX）は extra `onnx`（`uv sync --extra ds --extra onnx`）。
