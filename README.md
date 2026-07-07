# harness-template（AIコーディング開発基盤）

チームが案件開発を AIコーディング中心（Claude Code / Codex）で回すための、再利用でき、使いながら良くしていける開発基盤。品質はモデルでなく「仕組み（自動検証・決まりごと・文書）」で担保する。**完了＝検証にすべて成功したときだけ（自己申告では完了にしない）**。

このリポジトリは1つの案件に対応する（1リポジトリ＝1案件）。設計・進め方の正本はリポジトリ内に置く：`docs/charter.md`（立ち上げ）・`docs/method.md`（開発の進め方）・`docs/decisions/`（決定 DEC）。案件固有の外部設計文書があれば `docs/charter.md` から参照する（README はテンプレートとして複製されるので、複製先に無いリポ外パスは書かない）。

## 使い方
```bash
uv sync --extra ds      # 依存をそろえる（Python 3.14。ds はデータサイエンスの上乗せ）
uv run status           # work/ の木から STATUS.md を作り直す（生成物・コミットしない）
uv run task-lint        # 作業単位の検査（ID重複・depends_on の指す先が無い・done↔検証、を失敗に）
uv run issue list       # 課題の一覧（issue check：作業単位との紐付けの整合）
uv run data list        # テーブル定義の一覧（data lint：定義の静的検査）
uv run verify           # 完了判定（作業単位＋課題＋テーブル定義の検査＋ruff＋mypy＋pytest）
uv run data --help      # DS プロファイルの入口（テーブル・特徴量・実験・モデルのカタログ）
uv run serve --help     # 配信プロファイルの入口（champion の FastAPI 配信。正本は docs/serve.md）
uv run agent --help     # LLMOps プロファイルの入口（AgentSpec の評価・カタログ。正本は docs/agent.md）
uvx pre-commit run --all-files   # コミット直前の検査
```

## 構成（意味のある 1 まとまり＝1 ディレクトリ）
- `docs/` … 案件レベルの文書：`charter.md`（立ち上げ）／`requirements/`（要件 REQ）／`data/`（テーブル定義の正本 YAML）／`decisions/`（決定 DEC・不変）／`learnings.md`（気づき）／`DoD.md`（完了の定義）
- `issues/` … 課題（発見された問題・リスク・疑問 ISS。置き場がローカルのときだけ実体を持つ）
- `work/` … 作業単位（エピック・タスク・調査・実験）。**親はフォルダ**。1 まとまりのもの（説明・SPEC・コード・結果・メモ）を同居させる。
  - `work/EP-01-foundation/item.md` … エピックの目的と計画の詳しさ
  - `work/EP-01-foundation/T-0001-*.md` … 軽いタスクはファイル 1 つ／`INV-*.md` … 調査
  - `work/EP-06-ds-experiment-loop/E-0001-*/` … 実験は自分のフォルダに仮説・設定・結果を同居
- `src/<pkg>/` … 再利用する共有コード（データ分割・評価・特徴量・テーブル定義など）／`tests/` … その単体テスト
- `.harness/config.toml` … 置き場の切り替え（データ・課題・メタデータの各URI）／`.harness/templates/` … 文書の型
- `data/` … データ実体（正本は config の保存先URI・不変・指紋で管理・コミットしない）
- `STATUS.md` … 全単位の進捗＋人の判断待ち（自動生成・コミットしない）

計画は近い作業だけ先に詳しくする：着手が近いエピックだけ直前に分解する。まだ分解していない状態は正常。
