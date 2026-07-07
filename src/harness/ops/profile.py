"""ops プロファイルの宣言。中核は config（profiles = [..., "harness.ops"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（fastapi・uvicorn・polars 等）はここから import しない
（プロファイルのモジュールは軽く保つ規約＝DEC-0013）。ci_lint は stdlib＋pyyaml のみ・yaml を
遅延取り込みするので、ここから import しても配信・DS の依存は引き込まない（serve/profile.py と同型）。
"""

from __future__ import annotations

from harness.ops import ci_lint
from harness.profiles import Profile

PROFILE = Profile(name="ops", pm_checks=(ci_lint.run_checks,))
