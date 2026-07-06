---
id: EP-12
kind: epic
status: done
title: ds/ 正しさの補修（レビュー指摘の genuine な欠陥を塞ぐ）
plan: detailed
requirements: [REQ-002]
created: 2026-07-05
---
# EP-12 ds/ 正しさの補修

## 目的
`docs/ds-review-2026-07-05.md`（Fable・5 並列レビュー）で確認した **genuine な正しさバグ**を、テスト先書きで塞ぐ。
構造の作り替え（共有ストレージ層の抽出・レジストリ汎用化・pandera 化・skops 化など）は Rule of Three で意図的に
先送りし（ISS-0006〜0011）、ここでは「結果が静かに誤る／保存が壊れる／下流環境が壊れる」欠陥だけを直す。

## 進め方（歩く骨組みは既存・各タスクは1ファイル群＝1PR）
`uv run verify` を全成功に保ったまま、部品ごとに独立して差し替える。各タスク＝テスト先書き（pre-fix で失敗を確認）
→修正→**別セッションの独立レビュー**→verify 緑で done（作る側と確かめる側を分ける）。

- **T-0040 合否・昇格の正しさ**：`eval.passes` の NaN fail-open／`promote_model` の向きをレジストリから解決／
  孤児 version ディレクトリで `load_model(version=None)` が壊れる、を修正。
- **T-0041 schema 検証の穴**：Datetime/Duration 型が一致しない・NaN が nullable/range をすり抜け・複合 primary_key 未検査・
  null 数で一意判定がぶれる、を修正。
- **T-0042 CV の頑健性**：`_predict` の陽性クラス解決（`classes_`）・`fold_indices` の重複 id 検出（join）・`run_cv` の
  train/valid 重なりと長さ検査。
- **T-0043 EDA ドリフト/相関の正しさ**：`psi` の裾ドリフト盲目（端ビンを開く）・`correlations` の NaN 汚染
  （pairwise-complete）。
- **T-0044 依存フロアと疎行列**：ds extra の floor を実使用 API に合わせ引き上げ（sklearn>=1.9・polars>=1.42）・
  `_to_numpy` が疎行列を密化しない。

## やらないこと（Rule of Three・別途 ISS）
共有ストレージ層の抽出（ISS-0006）／ExperimentSpec 型付け（ISS-0007）／レジストリ汎用化・data sources（ISS-0008）／
多クラス経路（ISS-0009）／checks 評価・pandera 導出（ISS-0010）／効率・TargetEncoder 層化（ISS-0011）。
`docs/structure-review-2026-07.md` §低の保留（skops・CLI 汎用化）も維持。
