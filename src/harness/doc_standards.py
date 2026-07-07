"""ドキュメント標準の検査（doc_standards）。

doclint（**書かれた参照が実在するか**＝dead link の検査）とは別物：こちらは DEC-0019（ドキュメント標準）の
機械化できる部分＝**文書の発見可能性と整合**を検査する。人間向け索引 `docs/README.md` を起点に、文書の腐り
（索引から辿れない孤立文書・凡例に無い ID 接頭辞・用語集の不整合）を verify で止める。core の検査
（プロファイル非依存）。stdlib のみに依存（`from harness import pm` は可）。

検査は 5 つ（T-0130 で 3 つ・T-0131 で導入 lede 検査・T-0132 で造語 denylist を追加）：
- **孤立検査**：`docs/*.md`（直下・非再帰。`docs/README.md` 自身は除外＝索引そのもの。`docs/archive/**` は
  下層なので対象外）が `docs/README.md` の本文にファイル名で現れる（＝リンクされている）こと。未リンク＝error。
- **凡例網羅**：`docs/**/*.md`（`docs/archive/**` を除く・再帰）で使われている ID 接頭辞
  （EP・T・E・INV・DEC・ISS・REQ）が、`docs/README.md` の凡例の節（見出しに「凡例」を含む節）に
  載っていること。使われているのに凡例に無い接頭辞＝error。
- **用語集整合**：`docs/glossary.md` が存在し、用語の見出し（`##` 以降の見出し行）に重複が無く、
  各見出しの直下に定義本文があること（本文の無い空見出し＝error）。
- **導入（lede）検査**：対象文書（`_LEDE_DOCS`）の H1 直後の最初の内容ブロックが**平文の段落**であること
  （見出し・箇条書き・HTML コメント・コードフェンス・表・引用で始まらない＝可視の平易な導入。
  DEC-0019 の「各正本文書は可視の平易な導入で始まる」の機械化できる部分。「導入が実際に平易か」は
  レビュー観点）。違反＝error。
- **造語 denylist**：`docs/**/*.md`（`docs/archive/**` と `docs/glossary.md`＝定義そのもの、を除く）で、
  用語集で標準語に対応づけた**最悪造語**（`_DENYLIST`）が、その文書から用語集の該当アンカー
  （`glossary.md#<anchor>`）へのリンク無しに使われている＝error（標準の言い換えを修正提案として示す。
  Google style「jargon は初出で定義するか定義へリンク」の機械化・Vale の禁止語検査の翻案）。

穏当な縮退（コピー先の案件を誤検知しない）：`docs/` が無い、または `docs/` を正本置き場として使っていない
（直下に .md が無く ID 接頭辞も使われていない）プロジェクトでは何も指摘しない。
免除は `_EXEMPT`／`_LEDE_EXEMPT`／`_TERM_EXEMPT`（ファイル名→理由）だけ。**理由必須**（空はValueError で
即失敗＝黙って免除しない。coverage_lint と同型）。免除を増やす前に「索引に 1 行足す」「導入を書く」
「用語集へリンクする」を先に検討すること。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 免除リスト：真に索引不要な docs 直下の文書だけ（ファイル名 → なぜ索引に載せないかの理由。空は不可）。
_EXEMPT: dict[str, str] = {}

# 導入（lede）検査の対象（docs/ 直下のファイル名）。刷新済み（＝可視の導入を持つ）文書だけを列挙する
# 段階導入の明示リスト（T-0131 でプロファイル文書・T-0132 で中核ルール文書を追加。ratchet：一度載せた
# 文書は退行すると error）。README.md（索引）と glossary.md（対応表）は一覧そのものなので対象にしない。
# archive/ は正本でないので対象外（docs 直下だけを列挙する）。
_LEDE_DOCS: tuple[str, ...] = (
    "agent.md",
    "serve.md",
    "ops.md",
    "method.md",
    "charter.md",
    "DoD.md",
    "template-copy.md",
    "learnings.md",
)

# lede 検査の免除リスト（ファイル名 → なぜ導入不要かの理由。空は不可）。_EXEMPT と同型。
_LEDE_EXEMPT: dict[str, str] = {}

# 造語 denylist：語 → (修正提案＝標準の言い換え, docs/glossary.md のアンカー)。
# **高精度・最小主義の線引き（DEC-0019）**：誤検出を避けるため、対象は用語集で標準語に対応づけを宣言した
# 「最悪造語」だけに限定する。jargon 全部の機械化はしない＝検査できると嘘をつかない正直な線引きで、
# 「標準用語か・造語を増やしていないか」の残りは review スキルのドキュメント観点が受け持つ。
# 語を足すときは、docs/glossary.md に定義（アンカー）がある語だけを、標準の言い換えとアンカーの組で足す
# （仕組みは汎用＝dict に 1 行足すだけで対象語が増える）。
# 注：gate 語彙の不統一（「門番」「関門」の混用）も候補だが、両語は用語集で別概念（blocking/advisory の別
# ／昇格の 2 段判定）として定義済みで、正当な併用が現存する。機械化は保留し review 観点に残す（同上の線引き）。
_DENYLIST: dict[str, tuple[str, str]] = {
    "金メッキ": ("実装の出力をコピーした（入力の作り方から導出できない）ハードコード期待値", "金メッキ"),
}

# 造語 denylist の免除リスト（docs/ からの相対パス → 理由。空は不可）。_EXEMPT と同型。
_TERM_EXEMPT: dict[str, str] = {
    "decisions/DEC-0019-documentation-standards.md": (
        "造語を廃止するドキュメント標準の決定そのものが、廃止対象の語を鉤括弧の引用（言及）で記述している"
        "（使用でなく言及。DEC は確定後に書き換えない記録）。"
    ),
}

# 文書中の ID 接頭辞（「接頭辞-数字」の形で使われているものを拾う）。凡例はこの全部を説明しなくてよいが、
# 使われている接頭辞は必ず凡例に載る（読者が索引で意味を引ける）こと。
_ID_RE = re.compile(r"\b(EP|INV|DEC|ISS|REQ|T|E)-\d")

# markdown の見出し行（# の数＝深さ）。凡例の節の切り出しと用語集の項目抽出に使う。
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# 索引の凡例の節を見つける印（見出しにこの語を含む節を凡例とみなす）。
_LEGEND_MARK = "凡例"

# 平文の段落と認めない先頭パターン：見出し（#）・HTML コメント・コードフェンス・表・引用・箇条書き・番号リスト。
# lede 検査は「H1 直後の最初の内容が散文である」ことだけを機械で見る（平易さの中身はレビュー観点）。
_NON_PROSE_RE = re.compile(r"^(?:#|<!--|```|~~~|\||>|[-*+]\s|\d+[.)]\s)")


def _validated_exempt(exempt: dict[str, str], label: str) -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for name, reason in exempt.items():
        if not reason.strip():
            raise ValueError(f"{label}[{name!r}] の理由が空。免除には人が読める理由が必須（doc_standards）")
    return exempt


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


def _first_content_line_after_h1(text: str) -> str | None:
    """H1（`# 題名` の行）の直後にある最初の非空行を返す。H1 が無い・後に内容が無いときは None。"""
    lines = text.splitlines()
    h1 = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if h1 is None:
        return None
    return next((line for line in lines[h1 + 1 :] if line.strip()), None)


def _lede_problems(docs: Path, exempt: dict[str, str]) -> list[pm.Problem]:
    """導入（lede）検査：対象文書の H1 直後の最初の内容が平文の段落（＝可視の導入）であること。"""
    problems: list[pm.Problem] = []
    for name in _LEDE_DOCS:
        if name in exempt:
            continue
        path = docs / name
        if not path.is_file():
            continue  # 文書ごと持たないプロジェクト（コピー先で領域を外した等）には課さない
        first = _first_content_line_after_h1(path.read_text(encoding="utf-8"))
        if first is None:
            problems.append(
                pm.Problem(
                    "error",
                    f"docs/{name}: H1（`# 題名`）とその直後の本文が無い。冒頭に題名と 2〜4 文の平易な導入"
                    f"（これは何か・なぜ在るか・誰が読むか）を置くこと（DEC-0019）",
                )
            )
        elif _NON_PROSE_RE.match(first.lstrip()):
            problems.append(
                pm.Problem(
                    "error",
                    f"docs/{name}: H1 直後の最初の内容が平文の段落でない（見出し・箇条書き・HTML コメント・"
                    f"コードフェンス等で始まっている）。機構の説明の前に 2〜4 文の平易な導入（これは何か・"
                    f"なぜ在るか・誰が読むか）を可視の本文として置くこと（DEC-0019。真に導入不要なら"
                    f" doc_standards の _LEDE_EXEMPT に理由つきで）",
                )
            )
    return problems


def _term_problems(docs: Path, exempt: dict[str, str]) -> list[pm.Problem]:
    """造語 denylist：最悪造語が用語集の該当アンカーへのリンク無しに使われていないこと（標準の言い換えを提案）。"""
    problems: list[pm.Problem] = []
    for path in _non_archive_docs(docs):
        rel = path.relative_to(docs).as_posix()
        if rel == "glossary.md" or rel in exempt:  # 用語集は定義そのもの（denylist の対象外）
            continue
        text = path.read_text(encoding="utf-8")
        for term, (suggestion, anchor) in _DENYLIST.items():
            if term in text and f"glossary.md#{anchor}" not in text:
                problems.append(
                    pm.Problem(
                        "error",
                        f"docs/{rel}: 造語 '{term}' が用語集リンク無しに使われている。標準の言い換え"
                        f"「{suggestion}」に置き換えるか、使用箇所を glossary.md#{anchor} へリンクすること"
                        f"（真に必要なら doc_standards の _TERM_EXEMPT に理由つきで。DEC-0019）",
                    )
                )
    return problems


def run_checks(root: Path) -> list[pm.Problem]:
    """ドキュメント標準の検査（孤立・凡例網羅・用語集整合・導入 lede・造語 denylist）。違反＝error。"""
    docs = root / "docs"
    if not docs.is_dir():
        return []
    exempt = _validated_exempt(_EXEMPT, "_EXEMPT")
    lede_exempt = _validated_exempt(_LEDE_EXEMPT, "_LEDE_EXEMPT")
    term_exempt = _validated_exempt(_TERM_EXEMPT, "_TERM_EXEMPT")
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
    problems += _lede_problems(docs, lede_exempt)
    problems += _term_problems(docs, term_exempt)
    return problems
