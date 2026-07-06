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
2. 動かす：`uv run agent run --spec <yaml> --input "<発話>"`（ツール往復ループ 1 実行）。スモークは
   `uv run agent run --test`（合成 spec＋合成 cases・無ネットワーク・verify 用＝実験の `--test` 必須の規律と同じ）。
3. 評価・保存：golden set（`[{id, input, expected}]`）を `run_agent_eval` に通し、`save_agent` で版として保存
   （負の結果も記録）。乱数は明示 `seed=` のみ（グローバル種禁止）。
4. 変種比較：結果を `metrics_<variant>.yaml` に残し `uv run agent experiments --results <dir>` でリーダーボード
   （ML の実験と共通の形式＝比較の作法を二重化しない）。
5. 昇格：`uv run agent promote --work <ID> --name <名> --version <版> --primary <指標> --threshold 名=値`
   （絶対関門＝閾値・相対関門＝現 champion に primary で勝つ。落ちたら非ゼロ終了）。現 champion の確認は
   `uv run agent champion --work <ID> --name <名>`。

## してはいけないこと
- verify 経路で実プロバイダ（実 API）を叩かない（dummy/cassette だけ＝無ネットワーク・DEC-0015）。
- AgentSpec に `temperature` を書かない（存在しないノブ＝宣言が嘘をつく。effort を宣言に固定する）。
- ネットワーク・ファイル I/O をするツールを TOOLS に登録しない（純粋・決定的な関数だけ）。
- 評価・合否・昇格の関門を自作しない（`run_agent_eval`／`promote_agent` が正本。fail closed＝NaN は不合格）。
