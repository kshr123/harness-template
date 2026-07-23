"""deliver プロファイルの宣言。中核は config（profiles = [..., "harness.deliver"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（holidays・openpyxl・fastapi）はここから import しない
（プロファイルのモジュールは軽く保つ規約）。wbs_lint は stdlib＋pyyaml＋pydantic のみに依存し、
祝日ライブラリは暦を実際に引くときにだけ遅延取り込みするので、ここから import しても extra を引き込まない。
"""

from __future__ import annotations

from harness.deliver import wbs_lint
from harness.profiles import Profile

PROFILE = Profile(name="deliver", invariant_checks=(wbs_lint.run_checks,), test_globs=("test_deliver_*.py",))
