"""agent プロファイルの宣言。中核は config（profiles = [..., "harness.agent"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（anthropic・fastapi・polars）はここから import しない
（プロファイルのモジュールは軽く保つ規約）。lint は stdlib＋pyyaml＋providers（軽い）のみ・
yaml を遅延取り込みするので、ここから import しても LLM SDK は引き込まない。
"""

from __future__ import annotations

from harness.agent import lint, schedule_lint
from harness.profiles import Profile

# agent プロファイルが所有するテスト（tests/ からの glob）。非 agent の案件では収集・型検査から外す
# （anthropic/fastapi を import する cassette/serve のテスト等。昇格の特性化は ds とも共有）。
PROFILE = Profile(
    name="agent",
    invariant_checks=(lint.run_checks, schedule_lint.run_checks),
    test_globs=("test_agent_*.py", "test_promotion_characterization.py", "test_promotion_rollback.py"),
)
