---
id: T-0103
kind: task
status: done
title: コア文書からプロファイル入口への導線（AGENTS のコマンド節に data・serve・agent の各 1 行）
created: 2026-07-07
depends_on: [T-0102]
verified_by: [tests/test_guardrails.py::test_core_docs_link_profile_entrypoints]
---
# T-0103 コア文書からプロファイル入口への導線

## 狙い
`AGENTS.md` の「コマンド」節は core（verify/status/task-lint）のみで、プロファイル CLI（data/serve/agent）への
導線が無い。新規セッションのエージェントが「何ができるか」を最初の 1 ファイルで掴めるよう、各プロファイル入口への
1 行を足す（立ち上がりコスト減）。coverage_lint（T-0088）は「コマンド→docs」の到達可能性を守るが、
「最初に読む正本（AGENTS.md）からの見つけやすさ」は別の関心＝このタスクで埋める。EP-20 の締め（docs のみ・最小）。

## 受け入れ基準
- **`AGENTS.md`**：「コマンド」節に各 1 行を追加する（既存行は変更しない）：
  - `uv run data --help` … DS プロファイルの入口（テーブル・特徴量・実験・モデルのカタログ）
  - `uv run serve --help` … 配信プロファイルの入口（champion の FastAPI 配信）
  - `uv run agent --help` … LLMOps プロファイルの入口（AgentSpec の評価・カタログ）
  （item.md 起草時は data/serve のみだったが、EP-22 で `agent` CLI が入ったため 3 本とも載せる。）
  文言は既存行のトーン（`… 一言説明` 形式）に合わせ、詳細は各正本 docs（docs/agent.md・docs/serve.md 等）に任せる。
- **`README.md`**：コマンド一覧に相当する節があれば同じ 3 行を足す。無ければ足さない（新節は作らない・最小）。
- **`tests/test_guardrails.py`（追記）**：導線の常在検査（下記）。
- 新しい CLI コマンド・新規 docs は作らない。doclint・coverage_lint を含め `uv run verify` 全体緑。

## 触ってよいファイル
`AGENTS.md`（コマンド節に 3 行）・`README.md`（該当節があれば 3 行）・`tests/test_guardrails.py`（追記）。
それ以外は触らない（docs のみのタスク）。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_guardrails.py::test_core_docs_link_profile_entrypoints`（**unit**）：このリポの `AGENTS.md` を読み、
  `uv run data`・`uv run serve`・`uv run agent` の 3 トークンが含まれることを検査する。期待トークンは
  `pyproject.toml` の `[project.scripts]` にあるプロファイル CLI（core 以外のスクリプト名）から**導出**できる形が
  望ましいが、二重実装になるなら 3 トークンのポリシー固定でよい（理由をテスト docstring に 1 行）。
- coverage_lint（既存）が引き続き緑＝トークン追加が既存検査と矛盾しないこと。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：追記がコマンド節のトーン・並び順（core→プロファイル）を壊していないか／
新規セッションのエージェントが AGENTS.md だけから各プロファイルの入口に到達できるか＝実測（新セッションで試す）／
README との重複が二重管理になっていないか）
