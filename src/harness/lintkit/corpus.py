"""検査が共有する読み取り基盤（lintkit）。1 回の verify で 1 度だけ作り、各ルールへ渡す。

各 lint が同じファイル走査・同じ ast 解析・同じ `relative_to(root).as_posix()` を個別に持っていたのを、
ここに集約する。P0 では土台（root・相対パス・ast 解析キャッシュ）だけを置き、対象集合（docs 集合・
python 集合）や散文抽出は、それを最初に使うフェーズで足す（投機的に作らない＝機構あたりの意味を保つ）。
"""

from __future__ import annotations

import ast
from pathlib import Path


class Corpus:
    """リポジトリを 1 度だけ読む土台。ルールはここから対象集合・解析結果を得る（重複走査をしない）。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._parse_cache: dict[Path, ast.Module | None] = {}

    def rel(self, path: Path) -> str:
        """リポジトリ相対パス。常に `/` 区切り（Windows でも `\\` にしない＝conventions 規則 5 と同じ作法）。"""
        return path.relative_to(self.root).as_posix()

    def parse(self, path: Path) -> ast.Module | None:
        """`.py` を 1 度だけ ast 解析してキャッシュする。構文が壊れていれば None。

        検査は構文検査の代役をしない（壊れたファイルは飛ばす）＝ruff/mypy が構文・型を見る、という分担を守る。
        同じファイルを複数のルールが解析しても、実際の parse は 1 回だけになる。
        """
        if path not in self._parse_cache:
            try:
                self._parse_cache[path] = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                self._parse_cache[path] = None
        return self._parse_cache[path]
