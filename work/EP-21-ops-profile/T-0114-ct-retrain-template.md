---
id: T-0114
kind: task
status: done
title: 継続学習（CT）雛形＝retrain.yml＋ci_lint 拡張（既存部品の結線のみ・実行しない）
created: 2026-07-07
depends_on: [T-0113]
verified_by: [tests/test_ci_lint.py::test_retrain_template_missing_promote_step_flagged]
---
# T-0114 CT 雛形 retrain.yml＋ci_lint 拡張

## 狙い
継続学習（CT）の雛形 `templates/ci/.github/workflows/retrain.yml`（schedule→experiment→`data monitor`→
閾値を満たせば promote）を置き、ci_lint を拡張してその**構造を verify で守る**。**新しい学習・昇格の
仕組みは作らない**＝既存部品（experiment・`data monitor`・`promote_model`/`data promote`）の**結線のみ**。
実行しない（Actions を動かさない・ネットワーク 0）＝T-0111 と同じ担保方式。

## 受け入れ基準
- **`templates/ci/.github/workflows/retrain.yml`**（新規）：`schedule`（cron）＋手動 `workflow_dispatch` トリガ→
  checkout→uv セットアップ→`uv sync --all-extras`→実験実行（雛形の実験スクリプト呼び出し・複製先が
  差し替える箇所をコメント明示）→`data monitor`（ドリフト確認・**門番にしない＝exit code で落とさない**思想を
  コメントで明記）→評価が閾値を満たしたときだけ promote、の骨格。閾値判定は既存の合否（`eval.passes` 系の
  出力）を使う前提の雛形コメントとし、**新スクリプトは足さない**。
- **`ops/ci_lint.py` 拡張**（実行しない・yaml で読むだけ）：
  - retrain.yml が在るとき：`schedule` トリガの有無・experiment→monitor→promote の step 系列の有無を検査
    （欠けたら error。verify.yml の検査（T-0111）は不変）。
  - retrain.yml が**無い**のは error にしない（CT は任意の雛形＝verify.yml と違い必須にしない）。
- **導線（DEC-0009/DEC-0016）**：`docs/ops.md` の CT 節に「雛形の複製手順・各 step が呼ぶ既存部品・
  閾値の差し替え箇所」を記載（doclint の templates/ 参照実在に通る形）。
- 新 CLI コマンドは足さない。src/ は ci_lint.py 以外変更しない。model registry/batch 推論等の再実装をしない。

## 触ってよいファイル
`templates/ci/.github/workflows/retrain.yml`（新規）・`src/harness/ops/ci_lint.py`（拡張）・
`docs/ops.md`（追記）・`tests/test_ci_lint.py`（拡張）。serve/ds/core・既存 verify.yml テンプレの内容は
変更しない（ci_lint の verify.yml 検査ロジックも不変）。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_ci_lint.py::test_retrain_template_missing_promote_step_flagged`（**unit**）：一時プロジェクトに
  promote step を**意図的に抜いた** retrain.yml を置く→error（欠落は構成から導く）。
- `test_ci_lint.py::test_retrain_template_missing_schedule_flagged`（**unit**）：schedule トリガを抜くと error。
- `test_ci_lint.py::test_no_retrain_template_is_ok`（**unit**）：verify.yml だけの一時プロジェクトで []
  （CT は任意＝誤検知しない）。
- `test_ci_lint.py::test_repo_retrain_template_passes`（**integration**）：自リポの retrain.yml が検査に通る
  （置いた雛形自身を verify で腐らせない）。
- `uv run verify` 全体緑。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：retrain.yml の step 削除・並べ替えの変異で lint が落ちるか実測／
雛形が既存部品**だけ**を呼んでいるか＝新スクリプトの密輸が無いか／monitor を門番にしていないか）
