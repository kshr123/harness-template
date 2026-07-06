"""DS プロファイルの宣言。中核は config（profiles = ["harness.ds"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（polars・sklearn）はここから import しない
（schema の静的検査は polars 無しで動く＝遅延取り込みの前提を保つ）。
"""

from __future__ import annotations

from harness.ds import schema
from harness.profiles import Profile

PROFILE = Profile(name="ds", pm_checks=(schema.data_lint,))
