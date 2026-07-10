---
id: T-0190
kind: task
status: done
title: 複製後も残る資産から一時単位（ISS・work）への設計根拠参照を剥がす
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_doc_source_lint.py::test_real_repo_durable_assets_have_no_mutable_refs
---
# T-0190 恒久資産 → 一時単位の参照を断つ

## 何を直したか
複製すると消える `issues/`（課題）と `work/`（作業単位）を、複製後も残る資産が設計の根拠として参照していた。
参照先が消えると doclint の死にリンク検査が落ち、緑にできない（EP-31 item.md にデッドロックの再現を記録）。
各参照を剥がし、経緯は本文の説明に書き直した（番号でなく「その課題が何だったか」を 1 文で）。

## 剥がした参照（発生源）
- `docs/core.md`：`ISS-0015` → 「正本ドキュメントに実在しないモジュール名の行が残る逆向きの腐りは未解決の穴」と説明。
- `docs/learnings.md`：`ISS-0010`（2 箇所）→ 「手書き検証を続けるか pandera へ導出するかは未決」。
- `docs/README.md`：ID 表の例 `ISS-0003` → プレースホルダ `ISS-<番号>`。
- `src/harness/doclint.py`：`ISS-0003`（死にリンク検査の由来）を説明に、`ISS-0001 等`（形式の例示）を `ISS-<番号> 等`。
- `src/harness/code_doc_lint.py`：`ISS-0015` → 逆向きの腐りの説明。
- `src/harness/coverage_lint.py`：`ISS-0014`（2 箇所）→ plain main が死角だった穴の説明。
- `src/harness/conventions.py`：`ISS-0002`（docstring）→ 削除。
- `src/harness/ds/experiment.py`：`ISS-0007`（2 箇所）→ threshold/thresholds の取り違えを塞ぐ説明。
- `src/harness/ds/cli.py`：`ISS-0009`（コメント）→ 「陽性 1 列に潰すと黙って誤るので全列を出す」。
- `src/harness/testing.py`：`ISS-0002`（コメント）→ 削除。
- `src/harness/issues.py`：形式の例示 `ISS-0001` → `ISS-<番号>`。

`issues/` のファイル自体は消していない（範囲外）。剥がした結果、対応する課題は誰からも参照されなくなってよい
（それが正しい状態）。

## 検証
`uv run verify` 全成功。回帰は `tests/test_doc_source_lint.py::test_real_repo_durable_assets_have_no_mutable_refs`
（複製後も残る資産に `work/`・`ISS` の設計根拠参照が 1 件も無いことを現リポで確かめる）。
デッドロックの解消は EP-31 item.md の再現手順で実測（clone → 空 → verify）。
