"""stats（ベイズ統計モデリング）プロファイルの宣言。中核は config（profiles=[..., "harness.stats"]）経由でだけ知る。

ここに載せるのは検査の結線とテストの所有宣言だけ。重い依存（pymc・nutpie・arviz）はここから import しない
（プロファイルのモジュールは軽く保つ規約＝discover_profiles が extra 未導入でも import できる。ds/serve/ops と同型）。
pm_checks はまだ無い（推論・診断・保存のコードは T-0213 以降で入り、必要な検査はそのとき束ねる）。
"""

from __future__ import annotations

from harness.profiles import Profile

# stats プロファイルが所有するテスト（tests/ からの glob）。stats を外した案件（profiles に harness.stats が
# 無い＝pymc 等の optional 依存が入っていない）では、収集除外（conftest の collect_ignore_glob）と mypy の
# 対象除外がこれを使い、pymc/arviz を import するテストを収集・型検査から外す。新しい stats テストは
# test_stats_*.py の名前に収める（ここへ 1 行足すのと同義＝2 つ目の台帳を作らない）。
_STATS_TEST_GLOBS = ("test_stats_*.py",)

PROFILE = Profile(name="stats", pm_checks=(), test_globs=_STATS_TEST_GLOBS)
