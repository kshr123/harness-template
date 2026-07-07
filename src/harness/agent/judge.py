"""LLM-judge（rubric 採点器）＝provider を束ねて `(y_true, y_pred) -> float` の純署名に見せる薄い層。

- `AGENT_METRICS`（`eval.py`）の `MetricEntry.fn` 契約は `(y_true, y_pred) -> float`（純関数・provider を
  持たない）。judge は provider が要るので、この契約自体は変えず（rubric は既存の expected（y_true）経路
  そのもの）、provider だけを `RubricJudge`（frozen・`__call__` が同じ純署名）に束ねる（T-0096）。
- `judge_user_text`/`judge_messages` は judge へ渡す入力の正準テンプレ（キー導出の 1 か所）：dummy 台本の鍵・
  cassette フィクスチャの鍵（`cassette_key(..., messages=judge_messages(...))`）・テストの期待、すべてがここを
  共用する。テンプレを変えると鍵がずれて fail closed の ValueError になる＝テンプレ安定は cassette 契約の一部
  （宣言では変えさせない＝`JUDGE_SYSTEM_PROMPT` はコード固定）。
- `parse_judge_score` は裸の `[0, 1]` 数値への全文一致だけを許し、それ以外は NaN（散文からの数値抽出・
  範囲外の clamp をしない）。緩いパースは応答ドリフト（モデルが説明文を付け始めた等）を隠す。NaN は
  `eval.passes` の既存規約でそのまま不合格になる（fail closed・L-009）＝0.0（明確な低評価）と欠測
  （パース不能）を区別する。
- このモジュールは軽い（stdlib＋`harness.agent.{providers,spec}` のみ）。`anthropic` は import しない
  （DEC-0013）。`goal.py`/`eval.py` も import しない（循環回避＝eval.py が本モジュールを import する側）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from harness.agent.providers import Provider, ProviderReply, build_messages, reply_text
from harness.agent.spec import AgentSpec

# judge の system prompt。宣言（goal.yaml の judge: 節）では変えられない＝パースの決定性と cassette
# キーの安定の契約の一部（テンプレ変更はフィクスチャの鍵をずらす＝T-0096 のミューテーション観点）。
JUDGE_SYSTEM_PROMPT = (
    "あなたは採点器（judge）です。与えられた採点基準（rubric）に照らして採点対象（candidate）を評価し、"
    "0.0 から 1.0 の数値だけを 1 行で返してください。説明・理由・単位・前後の文章は一切書かないこと。"
)

_SCORE_RE = re.compile(r"\A(0(\.\d+)?|1(\.0+)?)\Z")


def judge_user_text(rubric: str, candidate: str) -> str:
    """judge へ渡す user 発話の正準テンプレ（キー導出の 1 か所＝テスト・cassette・dummy 台本が共用）。"""
    return (
        f"採点基準（rubric）:\n{rubric}\n\n"
        f"採点対象（candidate）:\n{candidate}\n\n"
        "0.0 から 1.0 の数値だけを 1 行で返すこと。"
    )


def judge_messages(rubric: str, candidate: str) -> list[dict[str, Any]]:
    """judge へ渡す messages（`build_messages(judge_user_text(...))` そのもの）。"""
    return build_messages(judge_user_text(rubric, candidate))


def parse_judge_score(text: str) -> float:
    """judge の応答テキストを `[0, 1]` の float に変換する（fail closed）。

    strip 後の全文が `0`〜`1`（小数可）の裸の数値でなければ NaN（散文からの抽出・範囲外の clamp はしない）。
    """
    stripped = text.strip()
    if not _SCORE_RE.match(stripped):
        return float("nan")
    return float(stripped)


@dataclass(frozen=True)
class RubricJudge:
    """provider を束ねた LLM-judge。`__call__(y_true, y_pred) -> float` は `MetricEntry.fn` と同じ純署名。

    y_true は rubric（採点基準）・y_pred は candidate（採点対象）＝`Goal.expected`/出力の経路をそのまま流用。
    """

    provider: Provider
    spec: AgentSpec

    def __call__(self, y_true: str, y_pred: str) -> float:
        reply: ProviderReply = self.provider.reply(messages=judge_messages(y_true, y_pred), tools=(), spec=self.spec)
        return parse_judge_score(reply_text(reply))


def make_rubric_judge(*, provider: Provider, spec: AgentSpec) -> RubricJudge:
    """LLM-judge 採点器（rubric＝expected でモデルに 0.0〜1.0 を採点させる）。

    `AGENT_METRICS` の factory 契約（seed 位置引数）とは異なる keyword-only 署名＝レジストリの
    `Registry.build`（seed 位置引数）からは呼ばない前提。束ねは `goal.gate_from_goal`（goal.yaml の
    judge: 節から provider を作って渡す 1 か所）が行う。
    """
    return RubricJudge(provider=provider, spec=spec)
