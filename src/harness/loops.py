"""loops 運用モデルの語彙（core・**stdlib のみ**・DEC-0013/DEC-0017）。

Anthropic「Getting started with loops」（loop＝停止条件が満たされるまで作業サイクルを繰り返すエージェント）の
分類を、プロジェクト全体の運用モデルへ昇格したもの。ここに置くのは**語彙だけ**（宣言と検査の型）。
実行エンジン（scheduler・常駐 runner）は作らない＝時間起動は cron/CI schedule/Claude 側 /loop・/schedule
スキルに委ねる（DEC-0006/0008 の「再発明しない」・DEC-0017）。

4 類型と既存部品の対応（1 行ずつ）：
- turn：発話が起動・モデルの end_turn が停止（`agent.runtime.run_agent`＝実装済み・`max_turns` backstop）。
- goal：呼び出し時に宣言した成功基準を**評価器**が検査し、満たすまで続行させる
  （本タスク＝`agent.goal.GoalGate`／`run_agent_to_goal`。T-0095）。
- time：時間間隔で起動・cancel で停止（雛形と runbook のみ＝実行基盤は利用者環境。T-0097）。
- event：イベント駆動→triage（`agent monitor --file-issue` が前半円＝冪等起票。後半円は T-0098）。

`LoopSpec`（宣言をひとまとめにする型）は**作らない**：宣言の正本は AgentSpec と Goal 側にあり、core に
宣言の重複を作ると二重管理になる（EP-23 item.md の設計判断）。束ねる型が要るかは 2 個目の消費（ds sweep 等）
が現れたときに DEC-0012 で判断する。

依存は dataclasses/typing（stdlib）のみ。プロファイル（ds/serve/agent/ops）を import しない（DEC-0004）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

# 4 類型の語彙（分類そのもの。実行はしない）。
Trigger = Literal["turn", "goal", "time", "event"]


@dataclass(frozen=True, kw_only=True)
class StopDecision:
    """停止判定の結果。reason は人が読む文字列（"goal_met" 等）。

    enum にしない：消費は表示と来歴（ログ・CLI 出力）だけで、新しい理由の追加を型変更にしたくない
    （閉じた集合にすると新しい stop 理由を足すたびに型を直す羽目になる＝YAGNI）。
    """

    stop: bool
    reason: str


class StopCondition(Protocol):
    """停止条件の差し替え口。1 サイクルの出力を見て続けるか止めるかを判定する。

    骨組みでは**テキスト出力への門だけ**（`output: str`）。引数をもっと一般化する（構造化出力・複数指標の
    生スコアを直接渡す等）のは 2 個目の消費（ds sweep の閾値探索等）が実際に必要になってから
    DEC-0012 で判断する（早すぎる一般化はしない＝EP-23 item.md）。
    """

    def check(self, *, output: str, iteration: int) -> StopDecision: ...
