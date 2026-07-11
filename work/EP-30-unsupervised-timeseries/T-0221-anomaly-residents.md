---
id: T-0221
kind: task
status: todo
title: ANOMALY に住人を増やす（PyOD の条件登録・LOF の novelty=True 版・符号は包みで揃える）
created: 2026-07-11
depends_on: [T-0220]
verified_by: []
---
# T-0221 異常検知の住人

## 何が問題か
`ANOMALY` の住人は iforest と lof（novelty=False・(A) 専用）の 2 つだけ。PyOD の手法（ecod・knn 等）と、
帰納的に使える LOF が無い。実測（2026-07-11）で確認した契約差：
- PyOD の `decision_function` は「高いほど異常」（sklearn と符号が逆）。
- sklearn の `LOF` は `novelty=False` だと `score_samples` を持たない（AttributeError）。
  `novelty=True` で fit すれば新規行を `score_samples` で採点できる（帰納的）。

## やること
- pyod を optional extra にし、`importlib.util.find_spec` の条件登録で住人を足す（statsmodels と同じ作法）。
  最初の住人は少数（例 ecod・knn）。包む側で符号を「大きいほど異常」に揃える
  （PyOD はそのまま・sklearn 系は反転。向きの正本は T-0219 の契約テスト）。
- `lof_novelty`（novelty=True・inductive=True）を足す（(B) 経路に接続できる LOF）。
  既存の `lof`（novelty=False・(A) 専用・inductive=False）はそのまま残す（別の kind として共存）。

## やらないこと
- PyOD の網羅（住人は実需要が来た分だけ）。
- 閾値・等級化（スコアは事実の報告。閾値は使う側の宣言）。

## 受け入れ基準
- 新住人すべてが T-0219 の契約テスト（仕込んだ外れ行が argmax）と T-0220 の帰納性テストに
  **テスト側の変更なしで**合格する（レジストリ駆動なので登録だけで検査対象に入る、が確かめられる）。
- pyod 未導入の環境でも `harness.ds.unsupervised` の import が成功し、カタログに pyod の住人が出ない
  （条件登録の作法）。導入ヒント（extras_hint）が出る。
- `uv run verify` 全成功（`uv sync --all-extras` の環境で pyod のテストが skip されない）。
