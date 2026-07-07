---
id: T-0102
kind: task
status: done
title: 依存脆弱性監査の CI ジョブ（uv sync --all-extras から pip-audit・理由必須の ignore）
created: 2026-07-07
depends_on: [T-0101]
verified_by: [tests/test_guardrails.py::test_ci_has_dependency_audit_job]
---
# T-0102 依存脆弱性監査の CI ジョブ

## 狙い
エージェントが自律的に extra を足す運用（lightgbm/onnx/optuna/shap の実例）なのに、依存のサプライチェーン監査が
ゼロ。CI に独立ジョブを足し、**全部入り（`uv sync --all-extras`）の環境**を pip-audit 相当で監査する。
item.md の論点「合否に効かせるか（偽陽性対策）」はこのタスクで決める：**合否に効かせる（blocking）＋
理由必須の ignore リスト**で運用する（coverage_lint の `_EXEMPT` と同型＝黙った見逃しを作らない・fail closed）。

## 受け入れ基準
- **`.github/workflows/ci.yaml`**：`verify` とは別の `audit` ジョブを追加する。
  - 手順：uv セットアップ → `uv sync --all-extras` → pip-audit 相当を実行（例 `uv run --with pip-audit pip-audit`。
    ロックされた環境そのものを監査する呼び方を実装時に確認する）。
  - **Linux（ubuntu-latest）のみ**でよい（依存の脆弱性は OS 非依存・Windows matrix は不要＝CI コストを増やさない）。
  - **blocking**（失敗したら CI 赤）。ただし既知の許容脆弱性は `--ignore-vuln` 等の明示リストで免除し、
    **各 ID の隣に理由コメント必須**（理由の無い ignore は追加禁止、と workflow 内コメントに明記）。
  - `verify` ジョブの既存ステップは変更しない（監査は独立ジョブ＝verify の実行時間に影響させない）。
- **`tests/test_guardrails.py`（T-0100 のファイルに追記）**：配線の常在検査（下記）。
- **導線**：新しい CLI コマンドは増やさない（coverage_lint の対象外）。監査がどこで走るか・ignore の運用ルール
  （理由必須）は workflow 内コメントを正本とし、`docs/learnings.md` に 1 行残す程度でよい（docs の新設はしない）。
- 初回実行で実際に脆弱性が報告された場合：修正（バージョン更新）を優先し、更新できないものだけ理由付き ignore に
  載せる。このタスクの完了条件は **audit ジョブが緑**（空の ignore で緑ならそれが最善）。
- `uv run verify` 全体緑。

## 触ってよいファイル
`.github/workflows/ci.yaml`・`tests/test_guardrails.py`（追記）・`docs/learnings.md`（1 行）・
（脆弱性対応で必要な場合のみ）`pyproject.toml` のバージョン下限＋`uv.lock`（`uv lock` 再生成）。
`src/` は触らない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_guardrails.py::test_ci_has_dependency_audit_job`（**unit**）：`.github/workflows/ci.yaml` を yaml として
  読み、(1) `audit` ジョブが存在する、(2) その steps に `uv sync --all-extras` と pip-audit 相当の実行が含まれる、
  (3) `continue-on-error: true` が**付いていない**（blocking の退行防止）、を検査する。期待値はこのタスクで定める
  ポリシーから導出。
- 監査そのものの合否は CI の実行系で担保する（pytest からネットワークを叩く監査は行わない＝verify は
  ネットワーク 0 の原則を守る）。PR には audit ジョブが緑の Actions 実行ログを証拠として貼る。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：監査対象が本当にロック済みの全部入り環境か＝pip-audit が別の一時環境を見ていないか／
blocking が本物か＝わざと古い脆弱依存を一時的に指定して赤くなることを実測したか（変異テスト・確認後に戻す）／
ignore リストの運用ルール（理由必須）が workflow 内に明記されているか）
