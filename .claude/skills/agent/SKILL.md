---
name: agent
description: LLM エージェント（AgentSpec）を作る・評価する・昇格する際に自動参照。宣言（prompt＋model＋tools＋方針）を golden set で採点し、関門を通った版だけ champion にする。エージェント・LLM・プロンプト・AgentSpec・ツール呼び出し・golden set・LLMOps の語で発火。
---

# agent（LLM エージェント＝1 宣言・評価は無ネットワーク・昇格は関門つき）

エージェントの実体は **1 宣言（AgentSpec）＝prompt＋model＋tools＋方針**。ライフサイクルは ML と同型：
宣言 → golden set → 採点 → 合否 → 保存 → 昇格。契約の正本は `docs/agent.md`（AgentSpec のキー・ログ契約・
評価と合否）。verify 経路は dummy/cassette のみ＝**ネットワーク 0・extra 無しで全機能が検証できる**（DEC-0015）。

## 手順
1. 宣言を書く：AgentSpec の YAML（キーの正本は `src/harness/agent/spec.py`・未知キーは読み込みで失敗）。
   使える語彙は一覧コマンドから選ぶ：`uv run agent providers`（provider に書ける kind）・
   `uv run agent metrics`（thresholds に書ける採点器・向きつき）・`uv run agent tools`（tools に書ける kind）。
   `temperature` は書けない（現行モデルはパラメータごと廃止＝送ると 400。決定性は effort 固定＋記録再生・DEC-0015）。
   実運用は `provider: anthropic`（`uv sync --extra agent`・SDK は遅延 import・effort を送り temperature は送らない）。
   テスト/CI は `cassette`（記録再生・fail closed・無ネットワーク＝SDK 応答形状のガード。詳細は `docs/agent.md`）。
2. 動かす：`uv run agent run --spec <yaml> --input "<発話>"`（ツール往復ループ 1 実行）。スモークは
   `uv run agent run --test`（合成 spec＋合成 cases＋goal ループ・無ネットワーク・verify 用＝実験の `--test`
   必須の規律と同じ）。答えの成功基準を宣言できるとき（golden set の期待が一意に決まる）は
   `--goal-expected "<正解>"`（＋`--goal-threshold`/`--max-cycles`）で goal-based ループ（評価器ゲートが
   合格と言うまで続行・詳細は `docs/agent.md` の「loops」節）。
   自由文の成功基準（一意の正解が無い）は `goal.yaml`＋`llm_judge`（`--goal <goal.yaml>`。
   `--goal-expected` と併用不可）。verify では judge も `provider: dummy`/`cassette` を goal.yaml の
   `judge:` 節に宣言する（無ネットワーク・詳細は `docs/agent.md` の llm_judge 節）。
3. 評価・保存：golden set（`[{id, input, expected}]`）を `run_agent_eval` に通し、`save_agent` で版として保存
   （負の結果も記録）。乱数は明示 `seed=` のみ（グローバル種禁止）。
4. 変種比較：結果を `metrics_<variant>.yaml` に残し `uv run agent experiments --results <dir>` でリーダーボード
   （ML の実験と共通の形式＝比較の作法を二重化しない）。
5. 昇格：`uv run agent promote --work <ID> --name <名> --version <版> --primary <指標> --threshold 名=値`
   （絶対関門＝閾値・相対関門＝現 champion に primary で勝つ。落ちたら非ゼロ終了）。現 champion の確認は
   `uv run agent champion --work <ID> --name <名>`。
6. 配信：`uv run agent serve --work <ID> --name <名>`（champion を FastAPI で配信。`POST /invoke`
   `{"input": "<発話>"}`＝会話×ツール往復 1 回。provider は宣言に従う・実行ログは `artifacts/agent/runs/**`
   へ 1 行ずつ＝そのまま監視が読む。champion が無ければ起動時エラー。要 `uv sync --extra agent`）。
7. 監視：`uv run agent monitor`（実行ログの拒否/打ち切り率・コスト分位・ツール頻度。門番にしない＝常に
   exit 0・`--file-issue` で帯が要注意以上なら課題を冪等起票）。入出力の検査は `agent/guardrails.py`
   （`PiiRegexGuard`＝PII 正規表現スタブ・`validate_output_schema`＝JSON Schema 最小検証。詳細は `docs/agent.md`）。
   定期実行（time-based routine）は `templates/schedule/` をコピーする（正本は `docs/agent.md` の
   time-based 節）。止め方の宣言（停止コメント＋README の停止見出し）は必須＝欠けると schedule_lint が
   `uv run verify` で失敗にする。

## してはいけないこと
- verify 経路で実プロバイダ（実 API）を叩かない（dummy/cassette だけ＝無ネットワーク・DEC-0015）。
- AgentSpec に `temperature` を書かない（存在しないノブ＝宣言が嘘をつく。effort を宣言に固定する）。
- ネットワーク・ファイル I/O をするツールを TOOLS に登録しない（純粋・決定的な関数だけ）。
- 評価・合否・昇格の関門を自作しない（`run_agent_eval`／`promote_agent` が正本。fail closed＝NaN は不合格）。
