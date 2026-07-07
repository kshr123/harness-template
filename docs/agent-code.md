# agent のコード — どのファイルが何を担い、どう組まれているか

`docs/agent.md`（LLM エージェントの契約・CLI・ライフサイクル）の姉妹。こちらは**中身の設計**を説明する：
`src/harness/agent/` の各ファイルが何を担うか、内容がどこにどう書かれているかを、コードを読む前につかめる
ようにする。読み手は、agent プロファイルを理解したい・広げたいエンジニア（と、それを助けるエージェント）。
この文書が実装と食い違わないことは `code_doc_lint`（`uv run verify`）が保証する＝モジュールを足したのに
ここで触れていないと検査が落ちる。

## 設計の芯

1. **1 エージェント＝1 つの宣言**（`AgentSpec`＝prompt＋model＋tools＋方針）。学習済みバイナリではなく、宣言が
   正本でコードは読むだけ＝ML の「1 モデル＝1 バイナリ」と同型の位置づけを宣言で持つ。
2. **差し替え口はレジストリ**。プロバイダ（`PROVIDERS`）・ツール（`TOOLS`）・採点器（`AGENT_METRICS`）は名前つき
   カタログに登録し、宣言は名前で選ぶだけ。一覧コマンドはレジストリから機械生成＝実装と常に一致。
3. **決定性は effort 固定＋無ネットワークで作る**。現行モデルは temperature を受け付けないため、`AgentSpec` は
   temperature を持たず、再現性の軸は effort（推論の深さ）を宣言に固定して作る。検証（verify）は実 API を使わず
   dummy（合成応答）と cassette（記録再生）だけで全機能を回す（ネットワーク 0）。
4. **ライフサイクルは ML と同型**：**宣言 → golden set で採点 → 合否 → 保存 → 採用（champion） → 配信 → 監視**。
   ds の「モデルを作って選ぶ」と同じ形を、モデルの代わりに宣言で回す。
5. **中核とプロファイルの境界**。中核（`src/harness/`）は agent を知らない。agent は config
   （`profiles=[..., "harness.agent"]`）経由でだけ現れる。anthropic/fastapi はプロファイル経路の外では import
   しない（軽 import）。

## 全体像（流れとファイルの関係）

ML と同型のライフサイクルが左から右へ進む（`①宣言 → ②実行 → ③評価 → ④保存・採用 → ⑤配信・監視`）。
`experiment.py` が ③評価の一巡を束ねる。`providers.py`/`tools.py` は ②実行が使う部品。

```text
  ①宣言          ②実行             ③評価・実験          ④保存・採用     ⑤配信・監視
  spec.py        runtime.py        eval.py              store.py        app.py
  (AgentSpec) ─▶ (往復ループ)  ─▶  (AGENT_METRICS) ─▶   (保存・      ─▶ (FastAPI /invoke)
                 goal.py           judge.py             champion 昇格)  monitor.py
                 (停止ゲート)      experiment.py                        (実行ログ監視)

  ②実行が使う部品: providers.py（プロバイダ）・cassette.py（記録再生）・tools.py（ツール TOOLS）
  ガード・配線   : guardrails.py（入出力ガード）・lint.py / schedule_lint.py（宣言・雛形の lint）・
                  cli.py（uv run agent の入口）・profile.py（verify 結線）
```

## どのコードがどんな役割か

`docs/agent.md` のライフサイクルの段と対応する。

**宣言**
- `spec.py` … `AgentSpec`（prompt＋model＋tools＋方針）の型と、宣言 YAML の読み込み。

**プロバイダ（モデルの呼び先）**
- `providers.py` … プロバイダ抽象（Provider Protocol＋レジストリ `PROVIDERS`）。dummy（決定的な合成応答）・anthropic。
- `cassette.py` … 記録再生プロバイダ＝実 SDK 応答を固定フィクスチャとして無ネットワークで再生する（replay 専用）。

**ツール（エージェントが呼べる関数）**
- `tools.py` … レジストリ `TOOLS`＝純関数のツールと、provider へ渡す宣言形。

**実行**
- `runtime.py` … 往復ループ（発話→ツール→…）の純関数と、1 実行を JSONL に残すログ契約（`AGENT_LOG_FIELDS`）。
- `goal.py` … goal-based 停止ゲート（評価器が合格と言うまで続行する loop。`end_turn` の自己申告を検査で置き換える）。

**評価・実験**
- `eval.py` … 採点器（レジストリ `AGENT_METRICS`）と合否ゲート（`passes`）。exact_match（純関数）と llm_judge。
- `judge.py` … LLM-judge（rubric 採点器）＝provider を束ねて `(y_true, y_pred) -> float` の純関数の形にする。
- `experiment.py` … 評価の一巡（golden set → provider → 採点 → 合否）。fold は無い（全体に 1 回）。

**保存・採用（champion）**
- `store.py` … 宣言（AgentSpec）の保存・読み込み・一覧・昇格（LLMOps のライフサイクル中核）。

**配信・監視**
- `app.py` … champion（採用済み宣言）を配信する FastAPI アプリ（`POST /invoke`）。
- `monitor.py` … 実行ログ（`AGENT_LOG_FIELDS` の JSONL）の監視（`agent monitor` の中身・純関数・stdlib のみ）。

**ガード・配線**
- `guardrails.py` … 入出力のガードレール（入力の PII 検出スタブ・出力の JSON Schema 最小検証・stdlib のみ）。
- `lint.py` … エージェント宣言（`docs/agents/**/*.yaml`）の構造 lint（参照整合を verify で守る）。
- `schedule_lint.py` … 定期実行の雛形（`templates/schedule/`）の構造 lint（停止条件の宣言まで検査する）。
- `cli.py` … `uv run agent <サブコマンド>` の入口（typer）。
- `profile.py` … agent プロファイルの宣言（lint 群を verify に載せる）。中核はこれを config 経由でだけ知る。

## どこに・何が・どう書かれているか（内容の在り処）

| 内容 | 宣言（案件ごとに書く） | それを扱うコード |
| --- | --- | --- |
| エージェントの定義（prompt/model/tools/方針/effort） | `docs/agents/**/*.yaml`（AgentSpec） | `spec.py`（読み込み）・`lint.py`（検査） |
| 評価例（期待する出力つき） | golden set の YAML | `experiment.py`・`eval.py`（採点・合否） |
| 使える部品の在庫（プロバイダ・ツール・採点器） | —（機械生成） | `PROVIDERS`/`TOOLS`/`AGENT_METRICS` → `uv run agent <一覧>` |
| 実行の記録（往復・停止理由・コスト） | —（実行時に自動） | `runtime.py` の `AGENT_LOG_FIELDS`・`monitor.py`（読み） |
| 採用の合否ライン | goal / thresholds | `eval.py` の `passes`（champion 採用の絶対条件） |

## 拡張の継ぎ目（新しい部品はレジストリに 1 行）

| 足すもの | ファイル: レジストリ | 一覧コマンド |
| --- | --- | --- |
| プロバイダ（モデルの呼び先） | `providers.py`: `PROVIDERS` | `agent providers` |
| ツール（呼べる関数） | `tools.py`: `TOOLS` | `agent tools` |
| 採点器（合否の指標） | `eval.py`: `AGENT_METRICS` | `agent metrics` |
