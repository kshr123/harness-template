# harness（AIコーディング開発ハーネス・汎用コア）

チームが案件開発を AIコーディング中心（Claude Code / Codex）で回すための、再利用可能で進化し続ける開発ハーネス。品質はモデルでなく「仕組み（自動検証・規約・文書）」で担保する。**完了＝検証が緑（自己申告では完了にしない）**。

このリポジトリは Phase 0（PM層中核）の最小実装。設計は `../draft/output/` の設計文書群を正とする。

## 使い方
```bash
uv sync                 # 依存を同期（Python 3.14）
uv run status           # tasks/ と wbs.md から STATUS.md を導出
uv run task-lint        # 孤児検出（真の孤児だけ赤・outline と epic:none は許容）
uv run verify           # 完了判定＝check full（孤児＋STATUS 一致＋ruff＋mypy＋pytest）
uvx pre-commit run --all-files   # コミット直前の検査
```

## 構成（PM層中核）
- `projects/<案件>/charter.md`・`wbs.md` … 上位工程（意図＋計画の成熟度 `plan: outline|detailed`）
- `tasks/*.md` … タスク（葉＝存在と状態の唯一の情報源）／`tasks/STATUS.md` … 生成物（手編集禁止）
- `src/harness/` … CLI（typer）・PM ロジック・共通の検証コマンド／`checks.toml` … 検証の登録先
- `AGENTS.md`（正本）・`CLAUDE.md`（@AGENTS.md）・`.claude/skills/`（session・verify）
- `learnings.md` … 教訓／`docs/DoD.md` … 完了の定義

計画は余白を持つ（ローリングウェーブ）：立ち上げは粗い WBS だけ。着手が近いエピックだけ直前に詳細化する。
