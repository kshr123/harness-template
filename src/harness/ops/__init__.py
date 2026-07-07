"""運用の上乗せ（プロファイル）。CI・継続学習・リリース戦略・監視の閉ループを扱う（EP-21）。

実行時の重い基盤（GitHub ランナー・k8s・クラウド）は利用者環境に委ね、当リポは**テンプレート＋
実行しない構造 lint（ci_lint）＋プロファイル境界＋スキル導線**で担保する（deploy_lint と同じ思想）。
中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）だけを見せる。
PROFILE の取り込みは軽い（重い依存を top で import しない・テストで固定）。
ops は CLI を持たない＝入口は正本 docs/ops.md と pm_checks（`uv run verify` に自動で乗る）。
"""

from harness.ops.profile import PROFILE

__all__ = ["PROFILE"]
