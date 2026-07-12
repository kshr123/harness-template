"""統計モデリング（ベイズ）プロファイル（harness.stats）。

ML の器（sklearn Pipeline・run_cv・点推定の指標）に押し込まず、独立したプロファイルにする。正本は
`InferenceData`（netCDF）で、背骨は「宣言→事前予測検査→推論→収束判定→事後予測検査→PSIS-LOO 比較→採用」。
ds と土台（Registry・storage・fingerprint・config・GATES・results/ の作法）は共有し、sklearn 由来の機構
（Pipeline・run_cv・out-of-fold・METRICS・leaderboard・FORMATS）は共有しない。正本ドキュメントは docs/stats.md。

このパッケージの top では重い依存（pymc・nutpie・arviz）を import しない（profile.py を軽く保つ規約＝
extra 未導入の環境でも `import harness.stats` が成功する）。実体は各工場の関数内で遅延 import する。
中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）だけを見せる。
"""

from harness.stats.profile import PROFILE

__all__ = ["PROFILE"]
