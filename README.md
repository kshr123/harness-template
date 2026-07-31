# harness-template（AIコーディング開発基盤）

- **読者**：人（このリポジトリを初めて触る開発者・チーム）
- **種別**：overview（全体像）
- **分かること**：この基盤が何で・誰のためか・どこに何があるか
- **ここからやること**：セットアップし、次の文書へ進む（人は [docs/README.md](docs/README.md)、エージェントは `AGENTS.md`）

## これは何か
- AI コーディング（Claude Code / Codex）中心で開発を回すための、**複製して使うプロジェクトテンプレート（土台）**。
- **1 リポジトリ＝1 案件**（顧客プロジェクト／開発テーマ）で丸ごと複製して使う（手順は [docs/template-copy.md](docs/template-copy.md)）。
- 案件に関わる **3 つの役割**が必要とするものを一式そろえてある：
  - **コンサル** … 案件の設計・進行・顧客への提出物（WBS・ガント）
  - **データサイエンティスト** … 実験・特徴量・モデル・評価
  - **エンジニア** … 配信・運用（API・監視・切り戻し）

## この土台が満たすこと
- **出す答えが黙って間違っていない。** 間違いはうるさく失敗させる（静かに間違えない）。
- **間違えたときに、何を間違えたか特定して戻せる。**
- **人の時間は、判断が本当に人のものである場所だけに使う。**
- **案件で得たものが次の案件へ渡り、改良が本体へ戻る。** この積み重ねの結果として「案件を重ねるほど強くなる」（2 案件目が 1 案件目より速く正しい）——これは目的そのものでなく、良い土台であることの帰結。

品質は人の注意力でなく、仕組み（自動検証・決まりごと・再利用部品・文書）で担保する。**完了は自己申告でなく、`uv run verify` が全部に合格したときだけ。**

## セットアップと主要コマンド
```bash
uv sync --extra ds      # 依存をそろえる（Python 3.14。ds はデータサイエンスの上乗せ）
uv run verify           # 完了判定（不変条件の検査＋ruff・mypy・pytest。内訳は docs/core.md）
uv run status           # work/ の木から STATUS.md を作り直す（生成物・コミットしない）
uv run task-lint        # 作業単位の検査（ID 重複・依存の指す先・done↔検証）
uvx pre-commit run --all-files   # コミット直前の検査
```
プロファイル別の使い始めコマンド（各正本 docs へ）：
- `uv run data --help` … データサイエンス（[docs/ds.md](docs/ds.md)）
- `uv run serve --help` … モデル配信（[docs/serve.md](docs/serve.md)）
- `uv run agent --help` … LLM エージェント（[docs/agent.md](docs/agent.md)）
- `uv run stats --help` … ベイズ統計（[docs/stats.md](docs/stats.md)）
- `uv run wbs --help` … 顧客向け WBS・ガント（[docs/deliver.md](docs/deliver.md)）

## どこに何があるか
- `docs/` … 人向けの文書。索引は [docs/README.md](docs/README.md)（読む順・ID 凡例・文書地図）
- `work/` … 作業単位（エピック・タスク・調査・実験）。**親はフォルダ**＝1 まとまりのもの（説明・SPEC・コード・結果）を同居させる
- `issues/` … 課題（発見した問題・リスク・疑問）
- `src/<pkg>/` … 再利用する共有コード ／ `tests/` … その単体テスト
- `data/` … データ実体（正本は config の保存先 URI。コミットしない）
- `.harness/` … 置き場の切り替え（`config.toml`）と文書の型（`templates/`）
- `AGENTS.md` … エージェント向けの決まりごと（`CLAUDE.md` が取り込む）
- `STATUS.md` … 全単位の進捗（自動生成・コミットしない）

## 次に読む
- **人**：[docs/README.md](docs/README.md) … 文書の索引・読む順・ID の凡例・文書地図
- **エージェント**：`AGENTS.md`（規則・作業単位の schema・コマンド索引）

## 覚える用語（3 つだけ）
- **案件** … 1 つの顧客プロジェクト／開発テーマ。1 リポジトリ＝1 案件で複製して使う。
- **正本** … ある事実・ルールの「唯一の正」とする置き場。同じ内容を 2 か所に書かない。
- **profile** … 中核（core）に領域別の部品と検査を足す束。ds・serve・agent・ops・stats を `.harness/config.toml` で有効化する。
