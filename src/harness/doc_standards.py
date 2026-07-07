"""ドキュメント標準の検査（doc_standards）。

doclint（**書かれた参照が実在するか**＝dead link の検査）とは別物：こちらは DEC-0019（ドキュメント標準）の
機械化できる部分＝**文書の発見可能性と整合**を検査する。人間向け索引 `docs/README.md` を起点に、文書の腐り
（索引から辿れない孤立文書・凡例に無い ID 接頭辞・用語集の不整合）を verify で止める。core の検査
（プロファイル非依存）。stdlib のみに依存（`from harness import pm` は可）。

T-0130 時点の検査は「即満たせるもの」3 つだけ（導入 lede 検査・造語 denylist は T-0131/0132 で足す）：
- **孤立検査**：`docs/*.md`（直下・非再帰。`docs/README.md` 自身は除外＝索引そのもの。`docs/archive/**` は
  下層なので対象外）が `docs/README.md` の本文にファイル名で現れる（＝リンクされている）こと。未リンク＝error。
- **凡例網羅**：`docs/**/*.md`（`docs/archive/**` を除く・再帰）で使われている ID 接頭辞
  （EP・T・E・INV・DEC・ISS・REQ）が、`docs/README.md` の凡例の節（見出しに「凡例」を含む節）に
  載っていること。使われているのに凡例に無い接頭辞＝error。
- **用語集整合**：`docs/glossary.md` が存在し、用語の見出し（`##` 以降の見出し行）に重複が無く、
  各見出しの直下に定義本文があること（本文の無い空見出し＝error）。

穏当な縮退（コピー先の案件を誤検知しない）：`docs/` が無い、または `docs/` を正本置き場として使っていない
（直下に .md が無く ID 接頭辞も使われていない）プロジェクトでは何も指摘しない。
免除は `_EXEMPT`（ファイル名→理由）だけ。**理由必須**（空はValueError で即失敗＝黙って免除しない。
coverage_lint と同型）。免除を増やす前に「索引に 1 行足す」を先に検討すること。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 免除リスト：真に索引不要な docs 直下の文書だけ（ファイル名 → なぜ索引に載せないかの理由。空は不可）。
_EXEMPT: dict[str, str] = {}

# 文書中の ID 接頭辞（「接頭辞-数字」の形で使われているものを拾う）。凡例はこの全部を説明しなくてよいが、
# 使われている接頭辞は必ず凡例に載る（読者が索引で意味を引ける）こと。
_ID_RE = re.compile(r"\b(EP|INV|DEC|ISS|REQ|T|E)-\d")

# markdown の見出し行（# の数＝深さ）。凡例の節の切り出しと用語集の項目抽出に使う。
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# 索引の凡例の節を見つける印（見出しにこの語を含む節を凡例とみなす）。
_LEGEND_MARK = "凡例"


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for name, reason in _EXEMPT.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{name!r}] の理由が空。免除には人が読める理由が必須（doc_standards）")
    return _EXEMPT


def _non_archive_docs(docs: Path) -> list[Path]:
    """docs/**/*.md（再帰）から docs/archive/** を除いた一覧。凡例網羅の走査対象。"""
    return sorted(p for p in docs.rglob("*.md") if p.relative_to(docs).parts[0] != "archive")


def _used_prefixes(docs: Path) -> set[str]:
    """docs/**/*.md（archive 除く）で「接頭辞-数字」の形で使われている ID 接頭辞の集合。"""
    used: set[str] = set()
    for path in _non_archive_docs(docs):
        used.update(_ID_RE.findall(path.read_text(encoding="utf-8")))
    return used


def _legend_text(readme_text: str) -> str | None:
    """docs/README.md から凡例の節（見出しに「凡例」を含む節。次の見出しまで）を切り出す。無ければ None。"""
    lines = readme_text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and _LEGEND_MARK in m.group(2):
            start = i + 1
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        if _HEADING_RE.match(line):
            break
        body.append(line)
    return "\n".join(body)


def _orphan_problems(docs: Path, readme_text: str, exempt: dict[str, str]) -> list[pm.Problem]:
    """孤立検査：docs 直下の .md（README 自身を除く）が索引の本文にファイル名で現れること。"""
    problems: list[pm.Problem] = []
    for path in sorted(docs.glob("*.md")):
        if path.name == "README.md" or path.name in exempt:
            continue
        if path.name not in readme_text:
            problems.append(
                pm.Problem(
                    "error",
                    f"docs/{path.name}: 索引 docs/README.md からリンクされていない（孤立文書）。文書地図の表に"
                    f" 1 行足すこと（真に索引不要なら doc_standards の _EXEMPT に理由つきで。DEC-0019）",
                )
            )
    return problems


def _legend_problems(docs: Path, readme_text: str) -> list[pm.Problem]:
    """凡例網羅：docs/**/*.md（archive 除く）で使われている ID 接頭辞が凡例の節に載っていること。"""
    used = _used_prefixes(docs)
    if not used:
        return []
    legend = _legend_text(readme_text)
    if legend is None:
        return [
            pm.Problem(
                "error",
                "docs/README.md: 凡例の節（見出しに「凡例」を含む節）が無い。ID・略語の凡例を置くこと"
                f"（説明が要る接頭辞: {', '.join(sorted(used))}。DEC-0019）",
            )
        ]
    problems: list[pm.Problem] = []
    for prefix in sorted(used):
        if not re.search(rf"\b{prefix}\b", legend):
            problems.append(
                pm.Problem(
                    "error",
                    f"docs/README.md: 凡例に ID 接頭辞 '{prefix}' が無い（docs/**/*.md で '{prefix}-<番号>' の形で"
                    f"使われている）。凡例の表に 1 行足すこと（DEC-0019）",
                )
            )
    return problems


def _glossary_problems(docs: Path) -> list[pm.Problem]:
    """用語集整合：docs/glossary.md が存在し、用語見出しに重複が無く、各見出しに定義本文があること。"""
    glossary = docs / "glossary.md"
    if not glossary.is_file():
        return [
            pm.Problem(
                "error",
                "docs/glossary.md が無い。造語・内部用語→平易な定義＋標準用語の対応表を置くこと（DEC-0019）",
            )
        ]
    lines = glossary.read_text(encoding="utf-8").splitlines()
    # 用語＝深さ 2 以上の見出し（# 1 つは文書題名なので用語に数えない）。本文＝次の見出しまでの非空行。
    entries: list[tuple[str, list[str]]] = []
    for line in lines:
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) >= 2:
            entries.append((m.group(2), []))
        elif entries:
            entries[-1][1].append(line)
    problems: list[pm.Problem] = []
    seen: set[str] = set()
    for term, body in entries:
        if term in seen:
            problems.append(
                pm.Problem("error", f"docs/glossary.md: 用語見出し '{term}' が重複している（正本は 1 か所。DEC-0019）")
            )
            continue
        seen.add(term)
        if not any(line.strip() for line in body):
            problems.append(
                pm.Problem("error", f"docs/glossary.md: 用語見出し '{term}' に定義本文が無い（空見出し。DEC-0019）")
            )
    return problems


def run_checks(root: Path) -> list[pm.Problem]:
    """ドキュメント標準の検査（孤立・凡例網羅・用語集整合）。索引から辿れない文書＝error。"""
    docs = root / "docs"
    if not docs.is_dir():
        return []
    exempt = _validated_exempt()
    readme = docs / "README.md"
    top_docs = [p for p in docs.glob("*.md") if p.name != "README.md"]
    if not readme.is_file():
        if not top_docs and not _used_prefixes(docs):
            return []  # docs を正本置き場として使っていない（コピー先の初期状態）＝誤検知しない
        return [
            pm.Problem(
                "error",
                "docs/README.md（人間向けの索引）が無い。読む順・凡例・文書地図を持つ索引を置くこと（DEC-0019）",
            )
        ]
    readme_text = readme.read_text(encoding="utf-8")
    problems = _orphan_problems(docs, readme_text, exempt)
    problems += _legend_problems(docs, readme_text)
    problems += _glossary_problems(docs)
    return problems
