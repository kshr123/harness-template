---
id: ISS-0009
kind: risk
state: resolved
found_in: ds-review-2026-07-05
created: 2026-07-05
promoted_to: T-0051
title: 二値分類がハードコードされ、多クラスを渡すと静かに誤った数字を出す
---
# ISS-0009 二値分類のハードコード（多クラスで静かに誤る）

## 事象
二値前提が複数モジュールに埋まっている：`cv._predict` は `predict_proba[:, pos]`（EP-12 で `classes_==1` の列に
修正したが陽性 1 クラス前提）、`eval._log_loss`/`confusion`/`class_metrics` は `labels=[0,1]` 固定、`_pr_auc` は
陽性クラスの意味を固定。`task: Literal["classification","regression"]` の型は多クラスを弾かないので、多クラス config は
**走ってしまい**、`proba` の 1 列だけを見た誤った指標を出す（例外にならない）。

## 根拠・影響
「段階1＝二値」は文書化済みだが、多クラスは最も起こりやすい次の要求。エラーで気づけず、もっともらしい数字が出るのが
危険。当面の最小策として `cv._predict` に「多クラスなら明示エラー」ガードを足せば、静かな誤りは防げる。

## 対処の方針（決めてから）
まず `_predict` に `len(classes_) != 2` の明示エラーを足して fail-loud に。拡張時は `task` を
`binary|multiclass|regression` の三値にし、解決は `metric_fn_for` の 1 箇所に集約（指標と予測の種類をそこで決める）。
最初の多クラス案件で着手。
