"""serve プロファイルの宣言。中核は config（profiles = [..., "harness.serve"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（fastapi・uvicorn・polars）はここから import しない
（プロファイルのモジュールは軽く保つ規約）。deploy_lint は stdlib＋pyyaml のみ・yaml を
遅延取り込みするので、ここから import しても配信依存（fastapi 等）は引き込まない。
"""

from __future__ import annotations

from harness.profiles import Profile
from harness.serve import deploy_lint

# 配信プロファイルが所有するテスト（tests/ からの glob）。非配信の案件では収集・型検査から外す
# （fastapi/uvicorn を import する app/cli/shadow のテスト。deploy_lint の構造テストも同じ prefix）。
PROFILE = Profile(name="serve", pm_checks=(deploy_lint.run_checks,), test_globs=("test_serve_*.py",))
