---
id: T-0096
kind: task
status: todo
title: goal の judge 化（rubric/LLM-judge 採点器）と goal の宣言化（YAML）
created: 2026-07-07
depends_on: [T-0095, T-0092]
verified_by: []
---
# T-0096 goal の judge 化と宣言化（outline・soon）

## 狙い
骨組み（T-0095）の goal は exact_match だけ＝答えが一意の場合に限られる。自由文の成功基準
（「手順が 3 段で書かれている」等）を **LLM-judge/rubric 採点器**として `AGENT_METRICS` へ足し、
goal ゲート（`GoalGate`）から**差し替え無しで**使えるようにする（ゲートは metric 名しか見ない設計の証明）。
あわせて goal を**宣言（YAML）**にする（コード内組み立てから卒業＝宣言が正本・DEC-0004 と同型）。

## 受け入れ基準の骨子（着手時に detailed 化）
- judge 採点器：verify 経路は **dummy judge（決定的・無ネットワーク）と cassette（記録再生・fail closed）**のみ
  （DEC-0015・T-0092 の `_reply_from_anthropic` 共有 adapter を流用）。実 judge は verify 経路外。
  向き・fail closed は `MetricEntry`／`passes` の既存規約のまま（新しい合否機構を作らない）。
- goal 宣言：`Goal` を YAML から読む口（`spec_from_mapping` と同じ extra forbid・未知キーは失敗）。
  AgentSpec に埋めるか別ファイルかは judge の引数（rubric 文）の形を見て着手時に決める。
- `agent metrics` カタログに judge が説明つきで載る（DEC-0009）。導線（docs/agent.md・スキル）同タスク。

## やらないこと
judge アンサンブル・pairwise/ELO（EP-22 item.md の later のまま）・goal の自動生成。
