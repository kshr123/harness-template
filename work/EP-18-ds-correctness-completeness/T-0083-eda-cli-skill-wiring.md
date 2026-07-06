---
id: T-0083
kind: task
status: done
title: eda 新関数の入口配線（data profile/CLI＋eda スキルに mutual_information・leakage_scan）
created: 2026-07-06
depends_on: [T-0082]
verified_by:
  - tests/test_cli_smoke.py::test_profile_with_target_adds_mutual_information_and_leakage
---
# T-0083 eda 新関数の DEC-0009 入口配線

## 背景
T-0082 で `mutual_information`・`leakage_scan` を eda.py に足したが、`data profile`/CLI にも eda スキルにも導線が無く、
エージェントが eda.py を読まない限り発見できない（DEC-0009 の入口未接続。T-0082 のレビュー指摘。T-0082 は「触ってよいファイル」を
eda.py に限定した仕様の矛盾で cli.py/スキルを触れなかった）。KS/Wasserstein は `compare` の列追加なので `data compare` に自動で
乗っており対応不要。本タスクで残り 2 関数の入口を閉じる。

## 受け入れ基準（DEC-0009・散文ガイドは作らない）
- `src/harness/ds/cli.py`：`mutual_information` と `leakage_scan` を CLI から呼べるようにする（既存 `data profile` の `--target`
  経路に載せるか、`data leakage`/`data mutual-info` 等の小コマンド。既存の表示流儀＝構造化表の print に合わせる）。
- `.claude/skills/eda/SKILL.md`：新しい入口（コマンド）へ導く 1 行を足す（一覧を手書きしない・カタログ/コマンドへ導くだけ）。
- 既存コマンド・表示は不変（追加のみ）。CliRunner か関数直呼びのスモークで exit 0・想定列が出ることを検査。

## 触ってよいファイル
`src/harness/ds/cli.py`＋`.claude/skills/eda/SKILL.md`＋`tests/test_cli_*.py`（実在名確認）。`eda.py` は触らない（T-0082 で確定済み・
関数を呼ぶだけ）。

## 検査（テスト先書き・構成から導く）
- CLI スモーク：target 付きテーブルで mutual_information の表・leakage_scan の表が出る・exit 0。
- doclint（`uv run check`）が SKILL.md の参照整合で緑。

## 独立レビュー（maker≠checker・差分のみ・実測）
異常なし。`data profile --target` に mutual_information・leakage の表が出る（exit 0）ことを CliRunner で実測・関数署名と噛み合う・
`--target` 無しでは新キー不在・既存キー不変。eda スキルは新入口へ 1 行で導く（散文ガイド増殖なし）。doclint 緑。変異 3/3 撃墜。
軽微：テストが既定 seed で呼ぶため「seed 転送忘れ」変異は捕まらない（差分で seed=seed 明示・実害なし）。
