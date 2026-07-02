---
id: T-0006
kind: task
status: done
title: 調査の種類・作成日/完了日・結論節の検査
requirements: [REQ-003]
verified_by: [tests/test_pm.py]
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0006 調査の種類・作成日/完了日・結論節の検査

## 目的
作業単位に調査（investigation）を加える。調査は変更ではなく知見・決定を成果物とし、`verified_by` は不要な代わりに、
done のとき本文の「結論」の節を検査で要求する。作成日・完了日（created・closed）を持たせ、時系列の並べ替えの材料にする。

## 受け入れ基準
- `kind` に investigation を追加し、`INV-` のファイルを作業単位として検出する。
- done の調査は「## 結論」の節が無いと検査で失敗する。
- 調査は verified_by を要求されない。
- `uv run verify` にすべて成功する。
