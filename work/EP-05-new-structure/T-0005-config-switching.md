---
id: T-0005
kind: task
status: done
title: 置き場の切り替え設定（.harness/config.toml）
requirements: [REQ-003]
verified_by: [tests/test_config.py::test_reads_file_and_layer_override]
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0005 置き場の切り替え設定

## 目的
データ・課題・メタデータの保存先を `.harness/config.toml` の URI で持ち、設定を変えるだけで
手元と共有先を切り替えられる骨格を作る。層ごとの backend 上書きも設定で表せるようにする。

## 受け入れ基準
- 設定ファイルが無ければ既定（ローカル）を返す。
- 層ごとの backend 上書きが効く（上書きが無い層は既定）。
- 壊れた設定は検証で失敗にする。
- `uv run verify` にすべて成功する。
