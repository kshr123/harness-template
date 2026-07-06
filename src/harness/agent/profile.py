"""agent プロファイルの宣言。中核は config（profiles = [..., "harness.agent"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（anthropic・fastapi・polars）はここから import しない
（プロファイルのモジュールは軽く保つ規約＝DEC-0013）。lint は stdlib＋pyyaml＋providers（軽い）のみ・
yaml を遅延取り込みするので、ここから import しても LLM SDK は引き込まない。
"""

from __future__ import annotations

from harness.agent import lint
from harness.profiles import Profile

PROFILE = Profile(name="agent", pm_checks=(lint.run_checks,))
