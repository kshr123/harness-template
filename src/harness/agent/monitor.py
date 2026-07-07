"""エージェント実行ログ（AGENT_LOG_FIELDS の JSONL）の監視（`agent monitor` の中身・純関数・stdlib のみ）。

runtime は「ログを書く側」・monitor は「読む側」。結合は JSONL の行スキーマ（正本は `agent/runtime.py` の
`AGENT_LOG_FIELDS`・docs/agent.md）**だけ**で、runtime の関数は呼ばない（`ds/monitor` が serve を import
しない結合規律と同型）。集計は**品質の代理（拒否/打ち切り率）・コスト（トークン/ターンの分位）・ツール使用**。

依存は stdlib のみ（numpy/polars/ds を import しない）：agent プロファイルは ds を import できず
（DEC-0004）、core は numpy を 1 つも持たない（DEC-0013 の軽さ）。基準分布との比較（psi）はしない＝
agent の実行ログに基準特徴表は無く、効く信号は拒否率とコストの素の集計（T-0093 の設計判断）。

監視は**門番にしない**：壊れ行・契約違反は警告して読み飛ばす（監視が盲目になるより縮退）。判定は
band（率の目安の離散化）として人が読む言葉で返し、exit code に載せない（CLI 側も常に exit 0）。
消費するキーだけを検証する（time/stop_reason/usage/turns/tools_used。request_id 等は見ない＝受け側は寛容に）。
"""

from __future__ import annotations

import json
import math
import warnings
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

# 率（non_end_turn_rate）の目安。表示のための離散化であって門番の閾値ではない（exit code に載せない）。
# 0.05 未満＝安定・0.05〜0.2＝要注意・0.2 以上＝大変化（psi_band の 0.1/0.25 と同じ 2 段の目安の作法）。
RATE_WATCH = 0.05
RATE_ALERT = 0.2

# コスト要約に使う分位（ds/monitor の prediction_summary と同じ p05〜p95）。
_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)


def rate_band(value: float) -> str:
    """率の目安を言葉にする（0.05 未満=安定・0.05〜0.2=要注意・0.2 以上=大変化。境界は上のバンドへ）。

    目安の離散化であって門番の閾値ではない（`agent monitor` は band によらず exit 0）。
    """
    if value < RATE_WATCH:
        return "安定"
    if value < RATE_ALERT:
        return "要注意"
    return "大変化"


@dataclass(frozen=True)
class AgentLogRow:
    """monitor が消費する 1 実行分（AGENT_LOG_FIELDS のうち消費 5 キーだけ・使わないキーは持たない）。"""

    stop_reason: str
    input_tokens: int
    output_tokens: int
    turns: int
    tools_used: tuple[str, ...]


@dataclass(frozen=True)
class AgentLogs:
    """読めた実行ログ。rows＝契約に適合した行・n_skipped＝読み飛ばした壊れ行の数（警告済み）。"""

    rows: tuple[AgentLogRow, ...]
    n_skipped: int

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _contract_error(row: object) -> str | None:
    """monitor が消費するキーの契約違反を返す（違反なし＝None）。契約は AGENT_LOG_FIELDS（docs/agent.md）。"""
    if not isinstance(row, dict):
        return "行が dict でない"
    if not isinstance(row.get("time"), str):
        return "time（str）が無い"
    if not isinstance(row.get("stop_reason"), str):
        return "stop_reason（str）が無い"
    usage = row.get("usage")
    if not isinstance(usage, dict) or not all(_is_int(usage.get(k)) for k in ("input_tokens", "output_tokens")):
        return "usage（dict: input_tokens/output_tokens int）が無い"
    if not _is_int(row.get("turns")):
        return "turns（int）が無い"
    tools = row.get("tools_used")
    if not (isinstance(tools, list) and all(isinstance(t, str) for t in tools)):
        return "tools_used（list[str]）が無い"
    return None


def read_agent_logs(files: Sequence[Path], *, since: date | None = None) -> AgentLogs:
    """エージェント実行 JSONL（AGENT_LOG_FIELDS の行スキーマ）を寛容に読む。

    壊れ行（JSON でない・消費キーの欠け/型違い）は**ファイルごとに 1 回警告して読み飛ばす**（門番にしない・
    n_skipped に数える）。since を渡すと time（ISO 8601）の日付がその日以降の行だけ残す（境界日を含む。
    絞り込みは壊れ行に数えない）。ネットワーク・ファイル書き込みはしない（読むだけ）。
    """
    rows: list[AgentLogRow] = []
    n_skipped = 0
    for path in files:
        bad = 0
        first_reason = ""

        def _skip(reason: str) -> None:
            nonlocal bad, first_reason
            bad += 1
            first_reason = first_reason or reason

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                _skip("JSON として読めない")
                continue
            reason = _contract_error(row)
            if reason is not None:
                _skip(reason)
                continue
            if since is not None:
                try:
                    at = datetime.fromisoformat(row["time"])
                except ValueError:
                    _skip("time が ISO 8601 でない")
                    continue
                if at.date() < since:
                    continue  # 期間外＝壊れ行ではない（警告しない）
            rows.append(
                AgentLogRow(
                    stop_reason=row["stop_reason"],
                    input_tokens=row["usage"]["input_tokens"],
                    output_tokens=row["usage"]["output_tokens"],
                    turns=row["turns"],
                    tools_used=tuple(row["tools_used"]),
                )
            )
        if bad:
            warnings.warn(
                f"{path}: 壊れ行 {bad} 行を読み飛ばした（最初の理由: {first_reason}。契約は docs/agent.md）",
                stacklevel=2,
            )
        n_skipped += bad
    return AgentLogs(rows=tuple(rows), n_skipped=n_skipped)


def _quantile_summary(values: Sequence[int]) -> dict[str, float]:
    """分位（p05/p25/p50/p75/p95）を**ニアレストランク法**で出す：昇順の値の `max(ceil(q*n), 1)-1` 番目。

    補間しない（実在する値だけを返す＝期待値をテスト入力の構成から直接導ける）。0 件は空 dict
    （数字を捏造しない）・1 件は全分位ともその値（ニアレストランクの自然な帰結）。
    """
    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    return {f"p{int(q * 100):02d}": float(ordered[max(math.ceil(q * n), 1) - 1]) for q in _QUANTILES}


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    """Counter を YAML 向けの決定的な並び（回数の多い順・同数は名前順）にする。"""
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


@dataclass(frozen=True)
class AgentMonitorReport:
    """監視表（`ds/monitor` の MonitorReport と同じ「正本→to_dict→YAML」の写像）。"""

    n_rows: int
    n_skipped: int
    stop_reason: Counter[str]
    non_end_turn_rate: float  # 1 − end_turn 率＝失敗/打ち切りの代理（品質スコアはログ契約に無い）
    max_turns_rate: float  # ツール往復の上限打ち切り率
    cost: dict[str, dict[str, float]]  # input_tokens/output_tokens/turns → 分位（_quantile_summary）
    tools_used: Counter[str]

    def to_dict(self) -> dict[str, Any]:
        """YAML 向けの dict（挿入順を保つ）。band は表示の目安＝ここで言葉にする（exit code には載せない）。"""
        return {
            "n_rows": self.n_rows,
            "n_skipped": self.n_skipped,
            "stop_reason": _counter_dict(self.stop_reason),
            "non_end_turn_rate": self.non_end_turn_rate,
            "non_end_turn_band": rate_band(self.non_end_turn_rate),
            "max_turns_rate": self.max_turns_rate,
            "cost": self.cost,
            "tools_used": _counter_dict(self.tools_used),
        }


def monitor(logs: AgentLogs) -> AgentMonitorReport:
    """実行ログの監視表。stop_reason 分布と率・コスト分位（トークン/ターン）・ツール使用頻度。

    0 行のとき率は 0.0（0 割を作らない・cost の分位は空 dict＝_quantile_summary の縮退）。
    ネットワーク・ファイル書き込みはしない（読むだけの純関数）。
    """
    stops = Counter(r.stop_reason for r in logs.rows)
    n = logs.n_rows
    non_end_turn_rate = 1.0 - stops.get("end_turn", 0) / n if n else 0.0
    max_turns_rate = stops.get("max_turns", 0) / n if n else 0.0
    cost = {
        "input_tokens": _quantile_summary([r.input_tokens for r in logs.rows]),
        "output_tokens": _quantile_summary([r.output_tokens for r in logs.rows]),
        "turns": _quantile_summary([r.turns for r in logs.rows]),
    }
    tools = Counter(name for r in logs.rows for name in r.tools_used)
    return AgentMonitorReport(
        n_rows=n,
        n_skipped=logs.n_skipped,
        stop_reason=stops,
        non_end_turn_rate=non_end_turn_rate,
        max_turns_rate=max_turns_rate,
        cost=cost,
        tools_used=tools,
    )
