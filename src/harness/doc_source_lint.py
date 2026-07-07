"""恒久ドキュメントが一時的な作業単位（work/）を参照していないかの検査（doc_source_lint）。

これは体裁でなく**複製時の壊れ（correctness）**の検査：doclint（参照が実在するか＝dead link）とは別で、
「恒久ドキュメントが、複製すると消える／置き換わるもの（`work/` の作業単位）に設計の根拠を置いていないか」を見る。
`work/` はエピック・タスク・実験の**進行を追う一時的な単位**で、テンプレートを新しい案件へ複製すると中身は
消える。恒久ドキュメント（README・AGENTS・`docs/*.md`）が `work/EP-21-…/item.md` のような特定の作業単位を
設計の正本として参照すると、複製先でリンク切れになり、正本が一時物に乗る。根拠は DEC（決定の記録＝恒久）か
本文の説明に置くべき。core の検査（プロファイル非依存）。stdlib のみに依存。

方針（誤検知を避ける＝高精度・低取りこぼし）:
- 対象は**恒久の読み手向けドキュメント**：`README.md`・`AGENTS.md`・`docs/*.md`（直下のみ）。ただし
  `docs/template-copy.md` は除く（複製手順そのものが「前案件の `work/` を消す」と説明する＝正当）。
  `docs/decisions/`・`docs/archive/`（履歴の記録）は直下でないので対象外。
- 禁じるのは**具体的な作業単位への参照**だけ：`work/EP-<番号>` / `work/T-…` / `work/E-…` / `work/INV-…`。
  プレースホルダ（`work/<エピック>/…`）は ID を持たないので拾わない（テンプレートの構成例は正当）。
- `artifacts/`・`results/`・`data/` は**契約のパス型**（`artifacts/serve/predictions/<名>/<日付>.jsonl` 等）で
  恒久ドキュメントに載るのが正しいので禁じない。作業単位 ID の provenance（DEC・learnings が「T-0095 で実装」
  と書く等）も履歴として正当なので、ここでは `work/…` パス参照だけを対象にする（過検出を避ける正直な線引き）。

免除は `_EXEMPT`（`ファイル名` → 理由）だけ。理由必須（空は ValueError＝黙って免除しない。coverage_lint と同型）。
検知したら直し方はメッセージに書く（DEC を指すか本文に根拠を書く）。免除を増やす前に「DEC/本文へ移す」を先に検討。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 禁じる参照：具体的な作業単位への `work/…` パス（プレースホルダ `work/<…>` は ID を持たないので当たらない）。
_WORK_REF_RE = re.compile(r"work/(?:EP|T|E|INV)-[0-9A-Za-z-]+")

# 対象から外す恒久ドキュメント（ファイル名 → なぜ work/ を参照してよいかの理由。空は不可）。
_EXEMPT: dict[str, str] = {
    "template-copy.md": (
        "複製の手順書。前案件の `work/EP-06-…` フォルダを「消す」対象として名指しする＝work/ への"
        "設計依存でなく work/ の扱いの説明なので、参照が正当。"
    ),
}


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for name, reason in _EXEMPT.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{name!r}] の理由が空。免除には人が読める理由が必須（doc_source_lint）")
    return _EXEMPT


def _durable_docs(root: Path, exempt: dict[str, str]) -> list[Path]:
    """恒久の読み手向けドキュメント（README・AGENTS・docs 直下の *.md）。免除ファイルは除く。無いものは飛ばす。"""
    docs: list[Path] = []
    for rel in ("README.md", "AGENTS.md"):
        p = root / rel
        if p.is_file() and p.name not in exempt:
            docs.append(p)
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        docs.extend(p for p in sorted(docs_dir.glob("*.md")) if p.name not in exempt)
    return docs


def run_checks(root: Path) -> list[pm.Problem]:
    """恒久ドキュメントが `work/` の作業単位を設計の根拠に参照していないか検査する。参照＝error。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    for path in _durable_docs(root, exempt):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for ref in _WORK_REF_RE.findall(line):
                problems.append(
                    pm.Problem(
                        "error",
                        f"{rel}:{lineno}: 恒久ドキュメントが一時的な作業単位 '{ref}' を参照している。"
                        f"`work/` は複製で消える／置き換わるので、設計の根拠は DEC（決定の記録）か本文の説明に"
                        f"置くこと（例：`work/EP-…/item.md の「やらないこと」` → 本文で理由を述べ `DEC-xxxx` を指す）。"
                        f"複製手順の説明なら docs/template-copy.md に書く（doc_source_lint）",
                    )
                )
    return problems
