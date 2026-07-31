# docs 索引

案件を進めるための文書の一覧。規則・コマンド索引（エージェントが毎セッション参照する正本）は
[../AGENTS.md](../AGENTS.md)。

| 文書 | 内容 |
| --- | --- |
| [../README.md](../README.md) | 全体像・主要コマンド・フォルダ構成 |
| [../AGENTS.md](../AGENTS.md) | 従うべき決まりごと（機械検査つき・正本） |
| [charter.md](charter.md) | この案件の目的・スコープ・成功条件 |
| [method.md](method.md) | 開発の進め方と、それ自体を進化させる仕組み・文書の書き方 |
| [DoD.md](DoD.md) | 完了の定義（チェックリスト） |
| [core.md](core.md) | `uv run verify` が回す検査の一覧（コード生成）と検査の足し方 |
| [ds.md](ds.md) | データサイエンス（表データの学習）の全体像と使いどころ |
| [ds-code.md](ds-code.md) | ds のコードの役割・組まれ方・設計 |
| [agent.md](agent.md) | LLM エージェント（AgentSpec）の契約・CLI・ライフサイクル |
| [agent-code.md](agent-code.md) | agent のコードの役割・組まれ方・設計 |
| [serve.md](serve.md) | モデル配信（FastAPI）と予測ログの契約 |
| [serve-code.md](serve-code.md) | serve のコードの役割・組まれ方・設計 |
| [ops.md](ops.md) | 運用（CI ゲート・継続学習・リリース戦略・監視の閉ループ） |
| [stats.md](stats.md) | ベイズ統計モデリング（モデル・サンプラー・診断・PPC） |
| [deliver.md](deliver.md) | クライアントに見せる WBS・ガント（作業単位の木からの生成ビュー） |
| [deliver-code.md](deliver-code.md) | deliver のコードの役割・描画/編集の設計 |
| [template-copy.md](template-copy.md) | この基盤を次の案件へ複製する手順 |
| [learnings.md](learnings.md) | 作業で得た気づきの記録（ルールにする前の材料） |
| [requirements/](requirements/) | 案件の要件（REQ） |
| [data/](data/) | テーブル定義の正本（YAML） |
| [../.claude/skills/](../.claude/skills/) | セッション中の作業手順（実験・レビュー・検証など） |

## ID の凡例
ID は「接頭辞-番号」で種類を表す。

| 接頭辞 | 意味 |
| --- | --- |
| `EP` | エピック（複数セッションにまたがる作業の束。例 `EP-01`） |
| `T` | タスク（1 つの変更。1 PR で完結。例 `T-0007`） |
| `E` | 実験（1 つの仮説の検証。例 `E-0001`） |
| `INV` | 調査（結論を出すための調べもの。例 `INV-0001`） |
| `ISS` | 課題（見つかった問題・リスク・疑問。`issues/`。例 `ISS-<番号>`） |
| `REQ` | 要件（`docs/requirements/`。例 `REQ-001`） |

## archive
[archive/](archive/) は日付付きの作業メモ（過去のレビュー記録・一時的な計画）の保管庫。正本ではない。
