"""serve プロファイルの宣言。中核は config（profiles への追加は T-0086）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（fastapi・uvicorn・polars）はここから import しない
（プロファイルのモジュールは軽く保つ規約＝DEC-0013。deploy_lint の pm_checks 追加は T-0086）。
"""

from __future__ import annotations

from harness.profiles import Profile

PROFILE = Profile(name="serve", pm_checks=())
