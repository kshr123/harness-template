---
id: T-0063
kind: task
status: done
title: バッチ推論入口（data predict＝champion を読み table に予測・版と指紋をログ）
created: 2026-07-06
depends_on: [T-0059]
verified_by:
  - tests/test_cli_predict.py::test_predict_champion_writes_parquet_and_sidecar
  - tests/test_cli_predict.py::test_predict_without_champion_raises
  - tests/test_cli_predict.py::test_predict_classifier_outputs_positive_proba
  - tests/test_cli_predict.py::test_predict_multiclass_writes_per_class_columns
  - tests/test_cli_predict.py::test_predict_rejects_prediction_column_collision
---
# T-0063 バッチ推論入口（data predict）

## 背景
学習した champion を「実際に使う」入口が無い（DEC-0009 の孤立）。保存済み champion を読み、入力テーブルに予測して
結果を書き出す `data predict` を足す。参考リポの FastAPI 実時間サービングを当リポ流儀（ローカル・バッチ・来歴付き）へ翻案。

## 受け入れ基準
- `ds/cli.py` に `data predict`（typer コマンド）：`--work <ID> --name <モデル名> --table <入力 table_id>
  [--version <版>（既定 champion）] [--out <出力パス>（既定 artifacts/predictions/<name>/<timestamp>/）]`。
  - champion（既定）または指定版を `models.champion`/`models.load_model` で読む（champion 不在なら分かる ValueError）。
  - 入力は `store.load(root, table)`（保存済みテーブル）。
  - 予測：分類（predict_proba あり）は陽性確率（`cv._predict` の proba＝ラベル 1 前提を再利用）、回帰（proba 無し）は
    predict の値。入力に予測列（例 `prediction`）を足した DataFrame にする。
  - 出力：`storage.atomic_write` で予測 parquet を書き、`storage.write_manifest` で sidecar yaml（model の
    work/name/version/fingerprint、入力 table_id、data 指紋、n_rows、created）を残す（**来歴付きの予測ログ**）。
    予測は store のスキーマ検証を通さない（派生成果物＝新スキーマ不要・raw で書く）。
- 認証情報を読まない。既存コマンド・関数は不変（追加のみ）。

## 触ってよいファイル
`src/harness/ds/cli.py`（新コマンド）＋`tests/test_cli_predict.py`（新規・typer CliRunner か直接関数呼び）。
`pipeline.py`/`eval.py`/`models.py`/`store.py`/`storage.py` は触らない（呼ぶだけ・並行作業あり）。必要な変更が出たら報告。

## 検査（テスト先書き・構成から導く）
- 小さな学習済みモデルを保存＋昇格 → 入力テーブルを store に保存 → `data predict` 実行 → 予測 parquet が
  入力行数ぶんの `prediction` 列を持つ・sidecar yaml に model version/fingerprint・data 指紋・n_rows が載る（構成から）。
- champion 不在・未知 table で分かる ValueError。
- 分類は陽性確率（[0,1]）・（回帰モデルなら値）を返す経路（構成した champion の種で確認）。

## 独立レビュー（2026-07-06・maker≠checker）
来歴の忠実性（fingerprint 群が実体由来）・champion 不在/未知 table の fail-loud・二値/回帰の正当性を実測で確認。
important 1：多クラス champion で `prediction` が黙って Array 列になり「陽性確率」の契約に反する（ISS-0009 の再演）
→ 予測種別を明示（二値=proba 1 列・回帰=value・多クラス=proba_0..k-1 の複数列）し、sidecar に `prediction_kind` を記録。
併せて予測列が入力の既存列と衝突したら ValueError（黙って上書きしない）。多クラス・衝突の回帰テスト追加。
minor（data_fingerprint の転記性・版不在メッセージ・--root/--out の細部）は据え置き（ローカルツールの範囲・記録）。

## 結果
実装・独立レビュー（多クラス明示＋列衝突ガード＋prediction_kind を反映）・verify 緑で done。
参考リポ バッチ推論＝ideal-build-plan Wave 3。champion の入口＝DEC-0009。
