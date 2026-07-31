"""lintkit — 検査の共有基盤。各 lint が重複して持っていた土台（対象集合・免除表・ID 文法・ast 解析）を
1 か所に集め、テストも 1 度だけにする。新しい検査を足すときの限界費用を下げるのが狙い（機構あたりの意味）。

- `Corpus`（corpus.py）… リポジトリを 1 度だけ読む土台（root・相対パス・ast 解析キャッシュ）。
- `Exemptions`（exempt.py）… 理由必須・fail-closed の免除表。
- `ids`（ids.py）… ID・プレースホルダ・語境界の文法。
- `Rule` … 名前つきの検査 1 つ（`scan(corpus) -> [Problem]`）。既存の `InvariantCheck`（`fn(root)`）は
  `Rule.from_callable` で包める＝プロファイル境界（`Profile.invariant_checks`）は変えずに移行できる。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness import pm
from harness.lintkit.corpus import Corpus
from harness.lintkit.exempt import Exemptions

__all__ = ["Corpus", "Exemptions", "Rule", "run"]


@dataclass(frozen=True)
class Rule:
    """名前つきの検査 1 つ。`name` はメッセージ・docs/core.md で使う安定 ID、`summary` は 1 行説明。"""

    name: str
    summary: str
    scan: Callable[[Corpus], list[pm.Problem]]

    @classmethod
    def from_callable(
        cls, fn: Callable[[Path], list[pm.Problem]], *, name: str | None = None, summary: str | None = None
    ) -> Rule:
        """既存の `InvariantCheck`（`fn(root) -> [Problem]`）を Rule に包む（移行の足場）。

        name/summary は指定が無ければ関数名・docstring 1 行目から採る（doc_sync の現行の採り方と同じ）。
        scan は corpus.root を渡して従来どおり呼ぶ＝挙動は不変。
        """
        doc = (fn.__doc__ or "").strip()
        return cls(
            name=name or fn.__name__,
            summary=summary or (doc.splitlines()[0] if doc else ""),
            scan=lambda corpus: fn(corpus.root),
        )


def run(rules: list[Rule], root: Path) -> list[pm.Problem]:
    """Corpus を 1 度だけ作り、各ルールの scan を走らせて Problem を集める。"""
    corpus = Corpus(root)
    out: list[pm.Problem] = []
    for rule in rules:
        out.extend(rule.scan(corpus))
    return out
