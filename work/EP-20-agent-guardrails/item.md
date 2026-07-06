---
id: EP-20
kind: epic
status: todo
title: エージェント運用のガードレール（秘密情報・破壊的操作・依存監査・来歴を機械で守る）
plan: outline
requirements: [REQ-001]
depends_on: [EP-19]
created: 2026-07-06
---
# EP-20 エージェント運用のガードレール

## 目的（エージェント開発・Ops の観点）
このリポは AIコーディング中心（AGENTS.md は Claude Code / Codex 共通の正本）。だが「エージェント運用そのものを守る機械的
ガードレール」が Claude Code のツール設定（`.claude/settings.json`）やシステムプロンプト頼みで、**別エージェント（Codex 等）や
コミット/push 経路では効かない**。リポ側の正本（pre-commit・CI・settings）に落として、どのエージェントでも効くようにする。

## 取り込み判断（agent-dev/ops 調査・now 層）
- **破壊的 git 操作の明示 deny**：`.claude/settings.json` の `permissions.deny` に `git push --force*`／`reset --hard*`／
  `clean -f*`／`branch -D*` 等。現状は Read 拒否（`.env`/`secrets`）のみ＝破壊操作は無防備。
- **秘密情報検出**：`.env`/`secrets` の Read 拒否だけで、コミットに鍵をハードコードする経路が無防備。`.pre-commit-config.yaml` に
  detect-secrets/gitleaks 相当を追加し、CI でも同じ入口で回す（ローカルと CI の検証入口を一致させる既存思想）。
- **依存脆弱性監査（サプライチェーン）**：エージェントが自律的に extra を足す運用（lightgbm/onnx/optuna/shap の実例）なのに
  監査ゼロ。CI 別ジョブで `uv sync --all-extras`→`pip-audit` 相当。合否に効かせるかは検討（偽陽性対策）。
- **コミット↔作業単位 ID の機械検査**：全コミットが `EP-xx T-xxxx：…` を冒頭に書く強い慣習だが未検査。`commit-msg` フックで
  `work/` 実在 ID を含むか検査（pm.py の ID 一覧を再利用）＝「何をどの根拠で変えたか」の来歴を一段強く。
- **コア文書からプロファイル入口への導線**：AGENTS.md の「コマンド」節は core のみ。`uv run data --help`／`uv run serve --help`
  への 1 行を足す（新規セッションの立ち上がりコスト減）。

## やらないこと（later・YAGNI）
コンテナ/K8s の実行時セキュリティ（イメージスキャン等＝DEC-0013 で実行基盤は利用者環境の関心と線引き済み）・エージェント専用
ゴールデン回帰ハーネスの新設（e2e スモーク＋CliRunner で既に充足）。

## 進め方（分解は着手直前に detailed 化）
T：破壊的 git deny＋秘密情報検出（settings.json＋pre-commit）／T：依存脆弱性監査（CI ジョブ）／T：commit-msg の作業単位 ID 検査／
T：コア文書の入口導線（AGENTS/README 1 行）。各々小粒度・既存ツール（pre-commit/CI/settings）の追加が中心で新規 src 資産は少。
EP-19 の coverage_lint 導入後に着手（新コマンド/文書の導線忘れを自動で止められる状態で進める）。
