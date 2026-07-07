# harness-template（AIコーディング開発基盤）

このリポジトリは、チームが開発を AIコーディング中心（Claude Code / Codex）で回すための開発の土台（テンプレート）です。
品質はモデルや人の注意力でなく、仕組み——自動検証・決まりごと・再利用できる部品・文書——で担保します。
仕事の完了は自己申告でなく、`uv run verify` という 1 つのコマンドがすべてに合格したかどうかで判定します
（**完了＝検証にすべて成功したときだけ**）。使いながら改善でき、次の案件へそのまま引き継げます。

**はじめて読む人は、まず [docs/README.md](docs/README.md) から辿ってください。**
読む順・ID の凡例・用語集・文書地図を持つ、人間向けの文書の索引です。

最初に 3 つの言葉だけ押さえれば読み進められます（他の内部用語は [用語集](docs/glossary.md) で引けます）：

- **案件**（[用語集](docs/glossary.md#案件)）… 1 つの顧客プロジェクト・開発テーマのこと。このテンプレートは
  「1 リポジトリ＝1 案件」で丸ごと複製して使う（手順は [docs/template-copy.md](docs/template-copy.md)）。
- **正本**（[用語集](docs/glossary.md#正本)）… ある事実・ルールの「唯一の正」とする置き場のこと。同じ内容を
  2 か所に書かない。設計・進め方の正本はこのリポジトリ内に置く：`docs/charter.md`（立ち上げ）・
  `docs/method.md`（開発の進め方）・`docs/decisions/`（決定 DEC）。案件固有の外部設計文書があれば
  `docs/charter.md` から参照する（README はテンプレートとして複製されるので、複製先に無いリポ外パスは書かない）。
- **profile**（[用語集](docs/glossary.md#profile)）… 中核（core）に領域別の部品と検査を足す束のこと。
  ds（データサイエンス）・serve（配信）・agent（LLM）・ops（運用）があり、`.harness/config.toml` で有効化する。

## 使い方（主要コマンド）
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
- `docs/` … 案件レベルの文書：`README.md`（索引）／`charter.md`（立ち上げ）／`requirements/`（要件 REQ）／`data/`（テーブル定義の正本 YAML）／`decisions/`（決定 DEC・不変）／`learnings.md`（気づき）／`DoD.md`（完了の定義）／`glossary.md`（用語集）
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
