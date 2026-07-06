---
id: EP-13
kind: epic
status: done
title: 中核メカニズムの整合（core↔ds のプロファイル分離・pm.lint 強化・config 整合）
plan: detailed
requirements: [REQ-001]
created: 2026-07-05
---
# EP-13 中核メカニズムの整合

## 目的
「core は汎用・ds はプロファイル」という宣言を実装でも成立させる。`docs/ideal-build-plan-2026-07-05.md` の Wave 1。
DEC-0010（理想形を今作る）に基づき、`docs/structure-review-2026-07.md` §中⑦・§低⑩の一部（境界の決壊）を前倒しで直す。

## 進め方（各タスク＝1 PR・テスト先書き・独立レビュー・verify 緑）
- **T-0045 core→ds 分離＋プロファイル機構**：`data_app`（14 サブコマンド）を `harness/ds/cli.py` へ移動／
  `harness/profiles.py`（config の `profiles=[...]` で読む）／`PM_CHECKS` を組み立て式にし checks.py の `from harness.ds`
  を除去／template-copy.md を「config 1 行を消すだけ」に更新。純移動中心＝既存テストが護る。
- **T-0046 pm.lint 強化**：`item.requirements` の REQ 実在検査（error）・未カバー REQ（info）・depends_on 循環検出（error）。

## やらないこと
config の URI 一元化（`parse_uri`）・`_root()` 上方探索は続く小タスクで（本エピック内 or Wave 4）。カタログ汎用化
（registry 統一）は EP-14。プロファイル機構は「置き場と登録の 1 ループ」に留め、汎用フレームワーク化はしない。
