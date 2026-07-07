"""配信の上乗せ（プロファイル）。champion を FastAPI で出す（sync 配信）。

土台の中核とは分けた配信固有の共有コード。`uv sync --extra serve` で fastapi・uvicorn を入れて使う。
中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）だけを見せる。
PROFILE の取り込みは軽い（fastapi・uvicorn・polars をここから import しない＝テストで固定）。
重い依存は app.py（fastapi）・cli.py（uvicorn）・runtime.py の関数内（polars/numpy）に閉じる。
"""

from harness.serve.profile import PROFILE

__all__ = ["PROFILE"]
