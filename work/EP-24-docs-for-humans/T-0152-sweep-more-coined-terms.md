---
id: T-0152
kind: task
status: done
title: 造語の掃き出し第2弾（入口→使える状態/コマンド・関門→合否判定・歩く骨組み→説明に・昇格は方向明示）
created: 2026-07-07
depends_on: [T-0151]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0152 分かりにくい造語をさらに平易にする

## 背景（オーナー指摘）
`入口`・`関門`・`歩く骨組み`は意味不明、`昇格`は「何から何へ」が不明、との指摘。living docs から掃き出す
（`正本`・`案件`は指摘外なので残す）。docs/decisions/（確定記録）・docs/archive/ は対象外。

## 置換方針
- **関門 → 合否判定**（絶対関門→絶対条件・相対関門→相対条件）。
- **歩く骨組み → 語を落として説明のみ**（「入力→処理→出力→検証が一巡する最小の実装」）。
- **昇格 → 方向を毎回明示**（2 つの意味を分ける）：
  - 気づき→ルール の文脈（method/learnings/harvest/AGENTS）＝**ルール化**。
  - モデル/エージェントの版→champion の文脈（agent/serve/ds/ops/experiment・serve スキル）＝**champion への採用**。
- **入口 → 意味ごとに平易化**：
  - 部品の「使えるようにする一式」（DEC-0009）＝「他の人が元コードを読まずに使える状態」に言い換え。
  - CLI/プロファイルの入口＝「使い始めるコマンド」。文書の入口＝「入り口（どこから読むかの案内）」。
  - 受け口・起点・経路など文脈に合う平易語へ。

## 受け入れ基準
- `uv run verify` 全成功（doclint がリンク整合を確認）。
- living docs に `入口`・`関門`・`歩く骨組み`・素の`昇格` が残っていない。文意・規範は変えない
  （AGENTS のルールは保持）。champion 文脈の「昇格」を「ルール化」に取り違えていない（learnings L-009 で確認）。

## 触ってよい範囲
`README.md`・`AGENTS.md`・`docs/*.md`（decisions/・archive/ を除く）・`.claude/skills/*/SKILL.md`・この item.md。
