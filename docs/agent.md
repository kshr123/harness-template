# agent — LLM エージェント（AgentSpec）の開発・評価の契約と CLI 導線

LLMOps/AgentOps プロファイル（EP-22・DEC-0015）。中核アーティファクトは **1 エージェント＝1 宣言
（AgentSpec＝prompt＋model＋tools＋方針）**。ライフサイクルは ML と同型：宣言 → golden set → 採点 →
合否 →（昇格・配信・監視は後続タスク）。実装は `src/harness/agent/`（spec.py＝宣言・providers.py＝
プロバイダ抽象・eval.py＝採点器と合否・experiment.py＝評価の一巡・lint.py＝宣言の構造 lint・cli.py＝入口）。

## 使い方

```
uv run agent providers                 # プロバイダ一覧（AgentSpec の provider に書ける kind）
uv run agent metrics                   # 採点器一覧（thresholds に書ける名前・向きつき）
uv run agent run --spec <yaml> --input "<発話>"   # 宣言で 1 応答（骨組みは dummy のみ）
uv run agent run --test                # 合成 spec＋合成 cases のスモーク（無ネットワーク・verify 用）
```

実プロバイダ（Anthropic SDK）は `uv sync --extra agent`（骨組みでは未使用・T-0092 で結線）。
**verify 経路は extra 無し・ネットワーク 0 で全機能が検証できる**（dummy/cassette のみ＝DEC-0015）。

## AgentSpec（宣言 YAML の契約）

正本は `src/harness/agent/spec.py`。キーはこれだけ（未知キーは読み込みで失敗＝extra forbid）：

| キー | 型 | 意味 |
| --- | --- | --- |
| `name` | str | エージェント名 |
| `provider` | str | PROVIDERS の kind（一覧は `uv run agent providers`） |
| `model` | str | モデル名（既定方針：`claude-opus-4-8`・高頻度は `claude-sonnet-5`＝DEC-0015） |
| `system_prompt` | str | システムプロンプト |
| `tools` | list[str]（省略可・既定 []） | TOOLS の kind（レジストリは T-0091。骨組みでは空が前提） |
| `effort` | low/medium/high/xhigh/max（既定 medium） | 推論の深さ。**宣言に固定**＝再現性の軸 |
| `max_turns` | int（既定 8） | ツール往復の上限（ループは T-0091） |
| `output_schema` | mapping（省略可） | 構造化出力の JSON Schema（検証は T-0093） |

**`temperature` は書けない**（現行モデルはパラメータごと廃止＝送ると 400・DEC-0015）。書くと専用の
エラーで effort＋cassette への移行を案内する。

## 評価と合否（golden set → passes）

- `run_agent_eval(spec, cases, provider=, metrics=, thresholds=, seed=)`：cases（`[{id, input, expected}]`）を
  provider に通し、採点器（AGENT_METRICS・骨組みは `exact_match`）の**平均**を出して `passes` で合否
  （向きつき・NaN は不合格＝fail closed）。fold は無い（golden set 全体に 1 回）。
- 乱数は明示 `seed=` のみ（グローバル種禁止）。dummy provider は入力＋seed の正準 JSON ハッシュから
  決定的に応答する（ネットワーク・課金ゼロ）。

## 宣言の構造 lint（verify に接続）

`docs/agents/**/*.yaml` を yaml で読むだけ（実行しない）で、`provider` が PROVIDERS に実在するかを検査する
（`src/harness/agent/lint.py`・serve の deploy_lint と同型）。`docs/agents/` が無いプロジェクトでは何も
指摘しない。`tools[]` の実在検査は TOOLS レジストリ（T-0091）と同時に足す。
