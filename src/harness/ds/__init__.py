"""データサイエンスの上乗せ（プロファイル）。

土台の中核（作業単位の木・検証コマンド）とは分けた、データサイエンス固有の共有コード。
`uv sync --extra ds` で numpy・polars を入れて使う。
中核へは `.harness/config.toml` の profiles 経由で PROFILE（検査の結線）だけを見せる。
PROFILE の取り込みは軽い（yaml・pydantic のみ）。重い依存は各モジュールで遅延取り込みする。
"""

from harness.ds.profile import PROFILE

__all__ = ["PROFILE"]
