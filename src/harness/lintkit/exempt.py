"""免除表の共有部品（lintkit）。理由必須・fail-closed（黙って免除しない）。

doc_source_lint・code_doc_lint・coverage_lint・boundary_lint が同じ「リポ相対パス → 理由（空は不可）」の
免除表と検証を個別に持っていた。ここに 1 度だけ実装してテストも 1 度だけにする。各検査は自分の免除項目を
渡して `Exemptions` を作るだけでよい。
"""

from __future__ import annotations

from collections.abc import Iterable


class Exemptions:
    """検査ごとの免除表。鍵はリポジトリ相対パス（`as_posix`）、値は人が読める理由（空は ValueError）。

    理由を必須にするのは、免除を増やすときに「なぜ免除してよいか」を残させるため（黙った免除を作らない
    ＝doc_source_lint / coverage_lint と同じ作法）。`check` で対象パスが免除されているかを問う。
    """

    def __init__(self, owner: str, items: dict[str, str] | None = None) -> None:
        self._owner = owner
        self._items = dict(items or {})
        for key, reason in self._items.items():
            if not reason.strip():
                raise ValueError(
                    f"{owner} の免除 {key!r} に理由が無い。免除には人が読める理由が必須（黙って免除しない）"
                )

    def __contains__(self, rel_path: str) -> bool:
        return rel_path in self._items

    def reason(self, rel_path: str) -> str | None:
        return self._items.get(rel_path)

    def filter(self, rel_paths: Iterable[str]) -> list[str]:
        """免除されていないものだけを順序を保って返す。"""
        return [p for p in rel_paths if p not in self._items]
