# docs 索引 — このリポジトリの文書の入り口（どこから読むかの案内）

このリポジトリは、AI（Claude Code など）に開発を任せても品質が崩れないようにするための**開発の土台**です。
仕事の完成は自己申告でなく、`uv run verify` という 1 つのコマンドがテスト・型検査・決まりごとの検査に
すべて合格したかどうかで判定します。文書・コード・検査はこの 1 リポジトリに同居し、新しい案件はリポジトリごと
複製して使います。このページは人間向けの索引で、どの文書を・どの順に読めばよいかをここから辿れます。

## 読む順（はじめての人へ）

1. [../README.md](../README.md) … 全体の 1 枚目（何ができるか・主要コマンド・フォルダ構成）。
2. [charter.md](charter.md) … この案件は何のためにあるか（立ち上げ文書）。
3. [method.md](method.md) … 開発の進め方と、進め方自体を改善する仕組み（考え方の核）。
4. [../AGENTS.md](../AGENTS.md) … 人と AI が従う決まりごと（強制ルールの正本）。
5. [DoD.md](DoD.md) … 「完了」と言ってよい条件のチェックリスト。
6. 必要な領域だけ：[ds.md](ds.md)（表データの学習）・[agent.md](agent.md)（LLM エージェント）・
   [serve.md](serve.md)（モデル配信）・[ops.md](ops.md)（CI・継続学習・監視）。

## ID・略語の凡例

文書中の ID は「接頭辞-番号」で種類を表す。

| 接頭辞 | 意味 |
| --- | --- |
| `EP` | エピック（複数セッションにまたがる作業の束。例 `EP-01`） |
| `T` | タスク（1 つの変更。1 PR で完結。例 `T-0007`） |
| `E` | 実験（1 つの仮説の検証。例 `E-0001`） |
| `INV` | 調査（結論を出すための調べもの。例 `INV-0001`） |
| `ISS` | 課題（見つかった問題・リスク・疑問。`issues/`。例 `ISS-0003`） |
| `REQ` | 要件（`docs/requirements/`。例 `REQ-001`） |

| 略語 | 意味 |
| --- | --- |
| `PSI` | Population Stability Index（分布のずれを測る監視指標） |
| `CV` | Cross-Validation（交差検証。データを分割してモデルを繰り返し評価する方法） |
| `CT` | Continuous Training（継続学習。定期的な再学習の自動化） |
| `PII` | Personally Identifiable Information（個人を特定できる情報） |
| `PM` | Project Management（プロジェクト管理。`src/harness/pm.py` の pm はこれ） |

## 文書地図（Diátaxis 分類）

文書は [Diátaxis](https://diataxis.fr) の 4 分類で読む目的を示す：**Tutorial**（手を動かして学ぶ）／
**How-to**（目的を達成する手順）／**Reference**（事実・契約の一覧）／**Explanation**（背景・なぜ）。

| 文書 | 分類 | 何が分かるか |
| --- | --- | --- |
| [../README.md](../README.md) | Reference | 全体像・主要コマンド・フォルダ構成 |
| [charter.md](charter.md) | Explanation | この案件の目的・スコープ・成功条件 |
| [method.md](method.md) | Explanation | 開発の進め方（最小の骨組みを先に作る）と、進め方自体を進化させる仕組み |
| [../AGENTS.md](../AGENTS.md) | Reference | 従うべき決まりごと（機械検査つき・正本） |
| [DoD.md](DoD.md) | Reference | 完了の定義（チェックリスト） |
| [ds.md](ds.md) | Reference | データサイエンス（表データの学習）の全体像と使いどころの地図 |
| [agent.md](agent.md) | Reference | LLM エージェント（AgentSpec）の契約・CLI・ライフサイクル |
| [serve.md](serve.md) | Reference | モデル配信（FastAPI）と予測ログの契約 |
| [ops.md](ops.md) | Reference | 運用（CI ゲート・継続学習・リリース戦略・監視の閉ループ） |
| [template-copy.md](template-copy.md) | How-to | この基盤を次の案件へ複製する手順 |
| [learnings.md](learnings.md) | Explanation | 作業で得た気づきの記録（ルールにルール化する前の材料） |
| [requirements/](requirements/) | Reference | 案件の要件（REQ） |
| [data/](data/) | Reference | テーブル定義の正本（YAML） |
| `../.claude/skills/` | How-to | セッション中の作業手順（実験・レビュー・検証など） |

Tutorial に当たる文書は現状無い（最も近いのは experiment スキル＋実験雛形 `E-0001` を写経する流れ）。

## archive

[archive/](archive/) は日付付きの作業メモ（過去のレビュー記録・一時的な計画）の保管庫。正本ではない。
