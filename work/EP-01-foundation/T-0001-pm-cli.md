---
id: T-0001
kind: task
status: done
title: プロジェクト管理の CLI（status / task-lint / verify）
requirements: [REQ-001]
verified_by: [tests/test_pm.py]
owner: sakurada
---
# T-0001 プロジェクト管理の CLI

## 目的
作業単位の木から STATUS を自動算出し、ID の重複や depends_on の指す先が無いことを見つけ、共通の検証コマンドで合否（成功/失敗）を返す。

## 受け入れ基準
- `uv run status` が STATUS.md を作る。
- `uv run task-lint` が、ID の重複・depends_on の参照エラーを失敗にする（未分解・未割り当ては許容）。
- `uv run verify` にすべて成功する。
