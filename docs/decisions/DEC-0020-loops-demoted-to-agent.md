---
id: DEC-0020
status: accepted
date: 2026-07-07
---
# DEC-0020 loops 語彙（Trigger・StopDecision・StopCondition）を core から agent へ降格する

## 状況（何を決める必要があったか）
DEC-0017 は「core 配置＝一般性が既に見えている」（DEC-0012 の判断軸）を根拠に `harness/loops.py` を core に
置いた。しかし同じ EP-23 の DEC-0018 は、その根拠を事後に検証して否定した：ds の実験 sweep は反復・
サイクルを持たない fan-out＋filter（`StopCondition` の 2 個目の消費ではない）・serve はリクエスト駆動で
loop の定義に当てはまらない（適用しない）・ops retrain は記述（位置づけ）のみで実コードの `StopCondition`
消費ではない。結果、`harness.loops` の実 import 消費者は `agent/goal.py` の 1 つだけで、`Trigger` Literal
（4 類型の分類そのもの）に至っては src/tests に定義行 1 件のみ（消費者ゼロ）のまま残っていた。

これは自リポの規律（DEC-0012：「消費者 1 つで抽象を core に切らない」・item.md が `passes` の core 昇格を
拒否した根拠と同型）に対する自己矛盾である：消費者 1 つの語彙を core に置き続け、消費者ゼロの語彙まで
コードに残していた。「配置＝消費の事実」を回復するかどうかを決める必要があった。

## 検討した選択肢
- A：現状維持（`harness/loops.py` を core に残す）。DEC-0017 の当初判断を変えない。
- B：**`StopDecision`・`StopCondition` を唯一の消費者 `agent/goal.py` へ畳み込み、`harness/loops.py` を削除。
  `Trigger`（消費者ゼロ）は復活させず削除する**。4 類型の分類自体は docs（DEC-0017・EP-23 item.md・
  docs/agent.md）の記述として残す（語彙の正本はコードでなく docs に置く）。
- C：`harness/loops.py` を空 re-export として残す（後方互換シム）。

## 決定と理由
**B を採用**。
- **DEC-0012 の判断軸に照らして core 配置の根拠が消えている**：DEC-0018 が「ds sweep は 2 個目の消費でない・
  serve は適用外・ops retrain は記述のみ」と確定させた時点で、`harness.loops` の実 import 消費者は
  `agent/goal.py` 以外に存在しない。消費者 1 つの抽象を core に置き続けるのは、まさに DEC-0012 が戒める
  「一般性が見えていないのに先回りして共有場所へ切り出す」形になっている。
- **`Trigger` は消費者ゼロの死んだ語彙**：4 類型（turn/goal/time/event）の分類そのものは価値があるが、
  コード上の `Literal` として存在する必要はない——分類は docs（DEC-0017・EP-23 item.md・docs/agent.md の
  写像表）で読めれば足りる。コードに残すと「使われているように見えて実は誰も import していない」という
  正直でない状態を固定してしまう。
- **C（空 re-export）は選ばない**：シムを残すこと自体が「死んだ語彙を削る」という本タスクの目的（正直化）に
  反する。消費者は `agent/goal.py` 1 つと分かっているので、そこへ実体を移すだけで済み、後方互換の橋を架ける
  必要がない（import 元は goal.py と両テストファイルのみ・grep で確認済み）。
- **過去 DEC は編集しない**：DEC-0017（core 配置の当初判断）・DEC-0018（適用範囲の確定）はいずれも意思決定の
  記録として正しい経緯を残す。本 DEC は DEC-0012 が DEC-0005 の一点（昇格タイミング）を上書きした先例と
  同型で、DEC-0017 の配置判断の 1 点だけを本 DEC が新しい記録として上書きする。

## core 再昇格の条件（恒久停止ではない）
`StopDecision`・`StopCondition`（および `Trigger`）を core へ戻す判断は、**2 個目の実 import 消費**
（`agent/goal.py` 以外のプロファイルが実際にこれらの型を import して使うコードが書かれたとき）が
出現した時点で、DEC-0012 の判断軸（一般的・再発する形が見えているか）に照らして判断する。候補は
DEC-0018 が名指しした ds sweep（sklearn `*SearchCV`／optuna で吸収できない反復制御が実案件で要ると判断
されたとき）と ops 閉ループ（T-0120 の実コード化）。

## 影響（良い点・悪い点・これからやること）
- 良い点：「配置＝消費の事実」という自己整合が回復する。`agent/goal.py` を読めば停止語彙の定義とその唯一の
  使用箇所が同じファイルにあり、core を経由する迂回がなくなる。墓標テスト
  （`tests/test_agent_goal.py`：`importlib.util.find_spec("harness.loops") is None`）が `harness.loops` の
  ゾンビ再導入（空 re-export の復活等）を機械的に止める。
- 悪い点：4 類型の分類がコードの型として一望できなくなり、docs（DEC-0017・EP-23 item.md・docs/agent.md）を
  正本として読む必要がある → 緩和：分類の記述は削除せず維持し、docs/agent.md・AGENTS.md から
  `agent/goal.py` への導線を残す。
- これからやること：2 個目の実 import 消費が実際に出現したら、まずこの DEC を superseded にして core
  再昇格を判断する（新しい抽象の置き場を先回りしない）。関連 [[DEC-0012]] [[DEC-0017]] [[DEC-0018]]。
