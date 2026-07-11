---
id: T-0084
kind: task
status: done
title: ONNX 保存形式（FORMATS 条件登録・sklearn 尾部のみ変換・data formats カタログ）
created: 2026-07-06
closed: 2026-07-06
verified_by: [tests/test_ds_models_onnx.py::test_binary_roundtrip_matches_sklearn, tests/test_catalog.py::test_formats_have_descriptions]
depends_on: [T-0049]
---
# T-0084 ONNX 保存形式

## 背景（DEC-0013・参考リポの中心＝可搬アーティファクト）
配信の可搬形式として ONNX を FORMATS に足す。当リポ Pipeline は polars 特徴＋sklearn 混成で、`to_numpy` という固定名の段が
numpy↔polars 境界。ONNX 化できるのは**その尾部（sklearn 部分）だけ**（本も純数値で同じ）。extra `onnx` は導入済み（b1b8b19）。

## 受け入れ基準（skl2onnx/onnxruntime 素通し・条件登録・DEC-0009）
- **新モジュール `src/harness/ds/onnx_format.py`**（models.py を肥らせない）。module top は stdlib＋numpy のみ・skl2onnx/onnxruntime/onnx は関数内遅延 import（skops と同じ作法）。
  - `_onnx_dump(model, path)`：Pipeline なら step 名 `"to_numpy"` の位置を探し、その後段（select?＋model）を tail として変換対象に（fit 済み段の再配線・refit しない）。無ければ全体。入力は `FloatTensorType([None, n_features])`。分類器は `options={id(tail):{"zipmap":False}}`（label＋proba の 2 出力）。多クラスは classes_ が 0..k-1 連番でなければ ValueError（cv._predict と同契約）。**metadata_props に JSON で feature_names/n_features/input_dtype="float32"/prediction_kind（proba|multiclass_proba|value）/classes/source="harness.ds" を焼き込む**（ファイル単体で自己記述＝可搬）。**保存時ラウンドトリップ自己検査**（決定的乱数で InferenceSession と tail の predict_proba/predict を allclose・不一致や変換不能は ValueError＝読めない保存を作らない）。
  - `_onnx_load(path)`：指紋照合済みパスを受け（load_model が照合後に呼ぶ）、metadata_props から prediction_kind で `OnnxClassifier`/`OnnxRegressor` を選び onnxruntime InferenceSession（providers=["CPUExecutionProvider"]）を包む。壊れ/metadata 無し/source 不一致は ValueError。
  - `OnnxClassifier`：`classes_`（int64 ndarray）・`predict_proba(x)->(n,k) float64`・`predict(x)->label`。`OnnxRegressor`：`predict(x)` のみ（predict_proba を持たない＝cli の hasattr 分岐がそのまま効く）。入力正規化＝polars DataFrame は feature_names で select→to_numpy→float32、numpy は列数検査→float32。これで `cv._predict` と互換＝`data predict` が無改修で onnx champion を使える。
- **`src/harness/ds/models.py`**：skops ブロックの直後に、`find_spec("skl2onnx") and find_spec("onnxruntime")` の両方が非 None のとき `FORMATS["onnx"]`（file_name="model.onnx"・description に「sklearn 尾部のみ・入力=特徴量済み float32」）を登録（onnx_format から import する 5 行程度）。ModelRecord/manifest スキーマは**不変**（影響半径を FORMATS 登録に閉じる）。
- **`data formats` カタログ**（`ds/cli.py`）：FORMATS を description つきで一覧する（`data models` 等と同型の render・FORMATS は dict なので薄い描画で可）。DEC-0009＝形式の入口。test_catalog に掲載検査を追加。
- 制限を docstring/description に明記：tfidf 等で tail 入力が疎になる構成・lightgbm 尾部（skl2onnx 非対応）・forecast は対象外＝dump 時に明示エラー。

## 触ってよいファイル
`src/harness/ds/onnx_format.py`（新規）・`src/harness/ds/models.py`（FORMATS 登録のみ）・`src/harness/ds/cli.py`（data formats のみ）＋
`tests/test_ds_models_onnx.py`（新規）・`tests/test_catalog.py`。`pipeline.py`/`eval.py`/`eda.py`/`cv.py`/`monitor` 系は触らない（並行あり）。

## 検査（テスト先書き・構成から導く・onnx は importorskip）
- 二値/多クラス/回帰の小 Pipeline を fit→save(format="onnx")→load→predict_proba/predict が sklearn と allclose。
- tail 切断（to_numpy あり/なし）・多クラス非連番で ValueError・lightgbm 尾部で明示エラー・壊れ onnx で ValueError。
- `data predict` が onnx champion＋特徴量テーブルで通る（e2e 1 本）。
- `data formats` に onnx/skops/pickle が description つきで載る。
- **Windows×3.14 の onnxruntime wheel を最初に確認**（無ければ owner に報告＝extra を外す判断。skip で誤魔化さない）。

## 独立レビュー（maker≠checker・差分のみ・実測）
別セッションの独立レビュアーが commit `ecca395` の差分を実測（二値/多クラス/回帰の allclose・tail 切断・
多クラス非連番/lightgbm 尾部/壊れ onnx の明示エラー・metadata_props 自己記述・保存時ラウンドトリップ自己検査・
`data predict` の e2e・`data formats` 掲載を確認）。Windows×3.14 の onnxruntime wheel 解決も確認済み。指摘反映後クリーン。
