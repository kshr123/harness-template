# docs 索引 — 人向けの文書の入り口

- **読者**：人（このリポジトリで作業する開発者・チーム）
- **種別**：overview（索引）
- **分かること**：どの文書を・どの順に・誰向けに読むか
- **ここからやること**：下の「読む順」に沿って必要な文書へ進む

- この基盤は AI（Claude Code など）中心で開発しても品質が崩れないようにする、**複製して使うテンプレート（土台）**。
- 完了は自己申告でなく、`uv run verify`（テスト・型検査・決まりごとの検査）が全部通ったときだけ。
- 文書・コード・検査は 1 リポジトリに同居し、新しい案件はリポジトリごと複製して使う。
- **エージェントの入口は [../AGENTS.md](../AGENTS.md)**（規則・schema・コマンド索引）。このページは**人の入口**。

## 読む順（はじめての人へ）
1. [../README.md](../README.md) … 全体像（何ができるか・主要コマンド・フォルダ構成）
2. [charter.md](charter.md) … この案件は何のためにあるか（立ち上げ）
3. [method.md](method.md) … 開発の進め方と、進め方自体を改善する仕組み（考え方の核）
4. [DoD.md](DoD.md) … 「完了」と言ってよい条件
5. [core.md](core.md) … 中核＝`uv run verify` が実際に何を回すか
6. 必要な領域だけ … ds / agent / serve / ops / stats / deliver（下の文書地図から）

規則そのものを引くときは [../AGENTS.md](../AGENTS.md)（人も読めるが、主にエージェントが毎セッション参照する正本）。

## ID・略語の凡例
ID は「接頭辞-番号」で種類を表す。

| 接頭辞 | 意味 |
| --- | --- |
| `EP` | エピック（複数セッションにまたがる作業の束。例 `EP-01`） |
| `T` | タスク（1 つの変更。1 PR で完結。例 `T-0007`） |
| `E` | 実験（1 つの仮説の検証。例 `E-0001`） |
| `INV` | 調査（結論を出すための調べもの。例 `INV-0001`） |
| `ISS` | 課題（見つかった問題・リスク・疑問。`issues/`。例 `ISS-<番号>`） |
| `REQ` | 要件（`docs/requirements/`。例 `REQ-001`） |

| 略語 | 意味 |
| --- | --- |
| `PSI` | Population Stability Index（分布のずれを測る監視指標） |
| `CV` | Cross-Validation（交差検証。データを分割してモデルを繰り返し評価する方法） |
| `CT` | Continuous Training（継続学習。定期的な再学習の自動化） |
| `PII` | Personally Identifiable Information（個人を特定できる情報） |
| `PM` | Project Management（プロジェクト管理。`src/harness/pm.py` の pm はこれ） |

## 文書地図（読者＋Diátaxis 分類）
分類は [Diátaxis](https://diataxis.fr) の 4 つ：**overview**（全体像）／**how-to**（目的を達成する手順）／**reference**（事実・契約の一覧）／**explanation**（背景・なぜ）。

| 文書 | 読者 | 分類 | 何が分かるか |
| --- | --- | --- | --- |
| [../README.md](../README.md) | 人 | overview | 全体像・主要コマンド・フォルダ構成 |
| [../AGENTS.md](../AGENTS.md) | エージェント | reference | 従うべき決まりごと（機械検査つき・正本） |
| [charter.md](charter.md) | 人 | explanation | この案件の目的・スコープ・成功条件 |
| [method.md](method.md) | 人 | explanation | 開発の進め方と、進め方自体を進化させる仕組み・文書の書き方の標準 |
| [DoD.md](DoD.md) | 人 | reference | 完了の定義（チェックリスト） |
| [core.md](core.md) | 人 | reference | 中核の正本。`uv run verify` が回す検査の一覧（コードから生成）と検査の足し方 |
| [ds.md](ds.md) | 人 | reference | データサイエンス（表データの学習）の全体像と使いどころ |
| [ds-code.md](ds-code.md) | 人 | explanation | ds のコードの役割・組まれ方・設計 |
| [agent.md](agent.md) | 人 | reference | LLM エージェント（AgentSpec）の契約・CLI・ライフサイクル |
| [agent-code.md](agent-code.md) | 人 | explanation | agent のコードの役割・組まれ方・設計 |
| [serve.md](serve.md) | 人 | reference | モデル配信（FastAPI）と予測ログの契約 |
| [serve-code.md](serve-code.md) | 人 | explanation | serve のコードの役割・組まれ方・設計 |
| [ops.md](ops.md) | 人 | reference | 運用（CI ゲート・継続学習・リリース戦略・監視の閉ループ） |
| [stats.md](stats.md) | 人 | reference | ベイズ統計モデリング（モデル・サンプラー・診断・PPC）の全体像 |
| [deliver.md](deliver.md) | 人 | reference | クライアントに見せる WBS・ガント（作業単位の木からの生成ビュー） |
| [deliver-code.md](deliver-code.md) | 人 | explanation | deliver のコードの役割・描画/編集の設計 |
| [template-copy.md](template-copy.md) | 人 | how-to | この基盤を次の案件へ複製する手順 |
| [learnings.md](learnings.md) | 人 | explanation | 作業で得た気づきの記録（ルールにする前の材料） |
| [requirements/](requirements/) | 人 | reference | 案件の要件（REQ） |
| [data/](data/) | 人 | reference | テーブル定義の正本（YAML） |
| `../.claude/skills/` | エージェント | how-to | セッション中の作業手順（実験・レビュー・検証など） |

## archive
[archive/](archive/) は日付付きの作業メモ（過去のレビュー記録・一時的な計画）の保管庫。正本ではない。
