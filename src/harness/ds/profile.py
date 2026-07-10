"""DS プロファイルの宣言。中核は config（profiles = ["harness.ds"]）経由でだけこれを知る。

ここに載せるのは検査の結線だけ。重い依存（polars・sklearn）はここから import しない
（schema の静的検査は polars 無しで動く＝遅延取り込みの前提を保つ）。
"""

from __future__ import annotations

from harness.ds import schema
from harness.profiles import Profile

# DS プロファイルが所有するテスト（tests/ からの glob）。非 DS の案件（profiles=[]）では収集・型検査から外す。
# polars・numpy・sklearn 等の DS 依存を import するファイルを網羅する（serve/agent と共有する data 依存の
# テストも含める＝ds を外したら収集しない）。新しい DS テストは既存の glob（test_ds_* 等）に収まる名前にするか、
# ここへ 1 行足す。
_DS_TEST_GLOBS = (
    "test_ds_*.py",
    "test_cli_*.py",
    "test_catalog.py",
    "test_forecast.py",
    "test_experiment_*.py",
    "test_e2e_*.py",
    "test_monitor_file_issue.py",
    "test_properties.py",
    "test_unsupervised.py",
    "test_storage.py",
    # data 依存（polars/numpy）を共有する配信・昇格のテスト（serve/agent とも共有・ds を外すと収集しない）。
    "test_serve_app.py",
    "test_serve_cli.py",
    "test_serve_shadow.py",
    "test_promotion_characterization.py",
)

PROFILE = Profile(name="ds", pm_checks=(schema.data_lint,), test_globs=_DS_TEST_GLOBS)
