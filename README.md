# harness（AIコーディング開発ハーネス・土台）

チームが案件開発を AIコーディング中心（Claude Code / Codex）で回すための、再利用でき、使いながら良くしていける土台。品質はモデルでなく「仕組み（自動検証・決まりごと・文書）」で担保する。**完了＝検証にすべて成功したときだけ（自己申告では完了にしない）**。

このリポジトリは第 0 段階（プロジェクト管理の中核）の最小実装。設計は `../draft/output/` の設計文書を正とする。

## 使い方
```bash
uv sync                 # 依存をそろえる（Python 3.14）
uv run status           # work/ の木から STATUS.md を作り直す
uv run task-lint        # 作業単位の検査（ID の重複・depends_on の指す先が無い、を失敗にする）
uv run verify           # 完了判定（作業単位の検査＋STATUS 一致＋ruff＋mypy＋pytest）
uvx pre-commit run --all-files   # コミット直前の検査
```

## 構成（意味のある 1 まとまり＝1 ディレクトリ）
- `projects/<案件>/` … 案件の設計（charter などの上流の文書）
- `work/` … 作業単位（エピック・タスク・実験）。**親はフォルダ**。1 まとまりのもの（説明・SPEC・コード・結果・メモ）を同居させる。
  - `work/EP-01-foundation/item.md` … エピックの目的と計画の詳しさ
  - `work/EP-01-foundation/T-0001-*.md` … 軽いタスクはファイル 1 つ
  - `work/EP-02-experiments/E-0001-*/` … 実験は自分のフォルダに仮説・設定・結果を同居
- `src/<pkg>/` … 再利用する共有コード（データ分割・評価・特徴量など）／`tests/` … その単体テスト
- `docs/decisions/` … 決定記録（永続の一意 ID）／`learnings.md` … 気づき／`docs/DoD.md` … 完了の定義
- `STATUS.md` … 全単位の進捗一覧（自動生成・比較のため別置き）／ MLflow … 指標の比較

計画は近い作業だけ先に詳しくする：着手が近いエピックだけ直前に分解する。まだ分解していない状態は正常。
