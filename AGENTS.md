# AGENTS.md — エージェント規約（正本）

このリポジトリは AIコーディング中心の開発ハーネス（汎用コア）。Claude Code / Codex 共通の正本。
Claude Code は `CLAUDE.md`（`@AGENTS.md` を取り込む）経由でこれを読む。

## 原則
- **完了＝検証が緑（done＝check 緑）**。自己申告で done にしない。`uv run verify` が緑になって初めて完了。
- **タスク（葉）が唯一の情報源**。1 タスク＝1 MD（`tasks/*.md`）。WBS/エピックは意図だけ手書きし、進捗は `uv run status` で導出（`tasks/STATUS.md` は生成物・手編集禁止）。
- **計画は余白を持つ（ローリングウェーブ）**。立ち上げは粗い WBS だけ。着手が近いエピックだけ直前に詳細化する。`plan: outline` のままは正常。

## 手順（1 タスク）
1. `tasks/<id>.md` を読む（該当タスクと本ファイルだけ。全タスクは読まない＝文脈を膨らませない）。
2. 実装する。範囲外は変更しない（確信がなければ手を出さず報告する）。
3. `uv run verify` を緑にする。緑の出力（証拠）を示す。テストは緩めない・消さない。
4. サブタスクは本文チェックリストで持ち、大きくなったら同じエピックの兄弟タスクへ昇格する。

## コマンド（実体は uv。make は使わない）
- `uv run verify` … 完了判定（check full＝孤児検出＋STATUS 一致＋ruff＋mypy＋pytest）
- `uv run status` … STATUS.md を再生成 / `uv run status --check` … 最新か判定
- `uv run task-lint` … 孤児検出（真の孤児だけ赤・outline と epic:none は許容）

## 禁止事項
- `tasks/STATUS.md` を手編集しない（生成物）。
- テストをゲーミングしない（答えのハードコード・テスト改変で緑にしない）。
- 認証情報を読まない・プロンプトに書かない（`.env`・`secrets/` は読み取り対象外）。

## 型・スタイル
- Python 3.14。型検査ゲート＝mypy（strict）。ty はローカル補助（任意）。整形/lint＝ruff。
