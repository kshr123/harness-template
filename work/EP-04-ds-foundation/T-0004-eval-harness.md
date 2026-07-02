---
id: T-0004
kind: task
status: done
title: 評価の仕組み（指標の算出と設定の閾値による合否）
requirements: [REQ-002]
verified_by: [tests/test_ds_eval.py]
depends_on: [T-0003]
owner: sakurada
---
# T-0004 評価の仕組み（指標の算出と合否判定）

## 目的
予測と正解から指標（正解率・AUC）を算出し、設定ファイルに書いた閾値で合否（成功/失敗）を返す
仕組みを作る。合否の機構は、共通の検証コマンドと同じ「成功/失敗」に接続できる形にする。

## 受け入れ基準
- `evaluate(y_true, y_score)` が指標（正解率・AUC）を返す。
- `passes(metrics, thresholds)` が、設定の閾値をすべて満たすときだけ成功を返す。
- 閾値は設定ファイル（辞書）で外から与えられ、コードに数値を埋め込まない。
- `uv run verify` にすべて成功する。
