# harness（AIコーディング開発ハーネス・土台）

チームが案件開発を AIコーディング中心（Claude Code / Codex）で回すための、再利用でき、使いながら良くしていける土台。品質はモデルでなく「仕組み（自動検証・決まりごと・文書）」で担保する。**完了＝検証にすべて成功したときだけ（自己申告では完了にしない）**。

このリポジトリは第 0 段階（プロジェクト管理の中核）の最小実装。設計は `../draft/output/` の設計文書を正とする。

## 使い方
```bash
uv sync                 # 依存をそろえる（Python 3.14）
uv run status           # tasks/ と wbs.md から STATUS.md を作り直す
uv run task-lint        # 参照チェック（存在しないエピックを指すタスクだけ失敗。未分解・未割り当ては許容）
uv run verify           # 完了判定（参照チェック＋STATUS 一致＋ruff＋mypy＋pytest）
uvx pre-commit run --all-files   # コミット直前の検査
```

## 構成（プロジェクト管理の中核）
- `projects/<案件>/charter.md`・`wbs.md` … 上流の計画（目的と、計画の詳しさ `plan: outline|detailed`）
- `tasks/*.md` … タスク（個々の作業＝存在と状態の唯一の情報源）／`tasks/STATUS.md` … 自動生成のファイル（手で編集しない）
- `src/harness/` … CLI（typer）・プロジェクト管理のロジック・共通の検証コマンド／`checks.toml` … 検証の登録先
- `AGENTS.md`（正本）・`CLAUDE.md`（@AGENTS.md）・`.claude/skills/`（session・verify）
- `learnings.md` … 気づき・使いにくかった点／`docs/DoD.md` … 完了の定義

計画は近い作業だけ先に詳しくする：立ち上げでは全体の見出し（エピック）だけを粗く置き、着手が近いものだけ直前に詳しく分解する。
