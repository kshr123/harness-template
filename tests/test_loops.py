"""core `harness.loops`（trigger×stop×policy の語彙）の単体テスト。

- `StopCondition` への適合の正本は mypy strict（構造的部分型）。実行時テストは `check` の返り値が
  `StopDecision` であることだけを確かめる。
- `harness.loops` の import が stdlib のみ（軽 import・DEC-0013）であることを、別プロセスの
  `sys.modules` で実測する（`tests/test_agent_lint.py` の既存 subprocess 作法と同じ）。
"""

from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

from harness.agent.goal import Goal, GoalGate
from harness.loops import StopCondition, StopDecision

pytestmark = pytest.mark.unit


def test_stop_condition_signature_stays_agent_shaped_until_dec() -> None:
    # loops.StopCondition.check は当面 agent 特化の (*, output: str, iteration: int) に固定（DEC-0018）。
    # ds/ops の 2 個目の消費が実在して初めて広げる＝そのときは DEC-0018 の再判断トリガを満たし
    # 新 DEC を書いてからこのテストを更新する（DEC-0012：ルール昇格は違反すると失敗する検査を先に）。
    sig = inspect.signature(StopCondition.check)
    params = list(sig.parameters.values())
    # self, output, iteration の 3 つ・output/iteration は keyword-only・output は str アノテーション
    assert [p.name for p in params] == ["self", "output", "iteration"]
    assert params[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[1].annotation == "str" or params[1].annotation is str


def test_goal_gate_check_returns_stop_decision() -> None:
    # GoalGate（agent プロファイル）が core の StopCondition を満たすことの実行時側の確認。
    gate = GoalGate(goal=Goal(expected="正解", thresholds={"exact_match": 1.0}))
    decision = gate.check(output="正解", iteration=1)
    assert isinstance(decision, StopDecision)
    assert decision.stop is True
    assert decision.reason == "goal_met"


def test_loops_module_import_is_stdlib_only() -> None:
    # harness.loops は core・stdlib のみ（プロファイル非依存＝DEC-0004/0013）。別プロセスで実測する。
    code = (
        "import sys\n"
        "import harness.loops\n"
        "heavy = [m for m in ('numpy', 'polars', 'sklearn', 'pandas', 'anthropic', 'fastapi', 'uvicorn')"
        " if m in sys.modules]\n"
        "assert not heavy, f'harness.loops の import が重い依存を読み込んだ: {heavy}'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
