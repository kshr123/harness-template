"""LLMOps/AgentOps の上乗せ（プロファイル）。LLM エージェント（宣言＝AgentSpec）を開発・評価・運用する。

中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）だけを見せる。
PROFILE の取り込みは軽い（anthropic・fastapi・polars をここから import しない＝テストで固定・DEC-0013）。
実プロバイダ（anthropic SDK）は extra `agent`（`uv sync --extra agent`）で入れ、verify 経路では使わない
（verify は dummy/cassette のみ＝無ネットワーク・DEC-0015）。
"""

from harness.agent.profile import PROFILE

__all__ = ["PROFILE"]
