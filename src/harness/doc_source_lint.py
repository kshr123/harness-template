"""恒久資産が一時的な作業単位（work/）・課題（issues/）を設計の根拠に参照していないかの検査（doc_source_lint）。

これは体裁でなく**複製時の壊れ（correctness）**の検査：doclint（参照が実在するか＝dead link）とは別で、
「複製すると消える／置き換わるもの（`work/` の作業単位・`issues/` の課題）に、複製後も残る恒久資産が
設計の根拠を置いていないか」を見る。`work/`（エピック・タスク・実験の進行を追う一時的な単位）と
`issues/`（見つかった問題・リスク・疑問）は、テンプレートを新しい案件へ複製すると中身が消える。
複製後も残る資産（README・AGENTS・`docs/*.md`・`src/harness/**`・`tests/**`・`templates/**`・
`.claude/skills/**`）が `work/EP-<番号>/item.md` や `ISS-<番号>` のような特定の一時単位を根拠として参照すると、
複製先で参照が宙に浮く／dead link になり、緑にできない（実際にこのデッドロックが起きた）。根拠は本文の説明に置くべき。
core の検査（プロファイル非依存）。stdlib のみに依存。

なぜ「残骸を grep する検査」ではないか（発生源＝参照の向きを塞ぐ）:
- 恒久資産 → 一時単位という**参照の向き**そのものを止める。消えた後の残骸を後追いで探すのではない。
- だから複製の前に（＝いま緑のうちに）向きの違反を機械で禁じる＝複製してもデッドロックが起きない状態を保つ。

方針（誤検知を避ける＝高精度・低取りこぼし）:
- 対象は**複製後も残る資産**：
  - `README.md`・`AGENTS.md`・`docs/*.md`（直下のみ）… 恒久ドキュメント。
  - `src/harness/**`・`tests/**`・`templates/**`・`.claude/skills/**` … 基盤コード・テスト・雛形・スキル。
  ただし `docs/template-copy.md` は除く（複製手順そのものが「前案件の `work/` を消す」と説明する＝正当）。
  `docs/archive/` 等の下層（履歴の記録）は直下でないので対象外。
- `issues/` 自身・`work/` 自身・`docs/learnings.md`・`docs/charter.md` は**走査しない**：いずれも案件領域
  （fork の init-project で消える／白紙化される）＝一時単位どうしの相互参照は正当（課題が作業単位を指す・
  気づきが課題を指す・憲章が自分の作業単位を指す等）。`docs/learnings.md` は L-### の定義元なので、
  ここを走査対象にすると定義自体を誤検知してしまう（案件領域の一覧は `_CASE_AREA_DOCS`）。
- **.py は散文（コメント＋docstring）だけを走査する**。文字列リテラル（関数の引数・アサーション）は対象外。
  理由：設計の根拠を書くのは人向けの散文（コメント・docstring）。一方テストは合成の一時ツリーを組む入力として
  `"work/EP-<番号>/…"` や `"ISS-<番号>"` を**データ**として渡す（現リポの実在単位を指してはいない）＝正当なので、
  データ文字列を拾わないことで過検出を避ける。dead link 側（実在検査）は doclint が別途受け持つ。
- `.md` など散文ファイルは全文を走査する。
- 禁じるのは**具体的な一時単位への参照**だけ：
  - `work/EP-<番号>` / `work/T-…` / `work/E-…` / `work/INV-…`
    （プレースホルダ `work/<エピック>` は ID を持たないので拾わない）。
  - `ISS-<番号>`（角括弧プレースホルダ `ISS-<番号>`・`ISS-XXXX` の型録表記は数字が続かないので拾わない）。
  - `L-###`（`docs/learnings.md` の気づき ID。定義元の learnings.md 自身は走査対象外なので誤検知しない）。
- `artifacts/`・`results/`・`data/` は**契約のパス型**なので禁じない。`T-…` 単体（`work/` の付かない provenance の
  地の文）も履歴として正当なので対象にしない（過検出を避ける正直な線引き）。

免除は `_EXEMPT`（リポジトリ相対パス → 理由）だけ。理由必須（空は ValueError＝黙って免除しない。coverage_lint と同型）。
検知したら直し方はメッセージに書く（本文に根拠を書く）。免除を増やす前に「本文へ移す」を先に検討。
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from harness import pm
from harness.lintkit.exempt import validate_exemptions

# 禁じる参照：具体的な一時単位への参照。
# work/ パス（プレースホルダ `work/<…>` は ID を持たないので当たらない）。
_WORK_REF_RE = re.compile(r"work/(?:EP|T|E|INV)-[0-9A-Za-z-]+")
# 課題 ID（角括弧プレースホルダ `ISS-<番号>` は数字が続かないので当たらない）。
_ISS_REF_RE = re.compile(r"ISS-\d+")
# 気づき ID（`docs/learnings.md` の L-###）。定義元は案件領域で fork のたびに白紙化されるので、恒久資産が
# これを根拠参照すると複製先で宙に浮く（work/・ISS と同じ壊れ方）。定義元の learnings.md 自身は走査しない。
_LEARNING_REF_RE = re.compile(r"\bL-\d{3}\b")
# 型録表記（`ISS-XXXX`・`ISS-0000` 形の説明用連番）はプレースホルダとみなして拾わない。
_PLACEHOLDER_RE = re.compile(r"XXXX|0000", re.IGNORECASE)

# docs 直下だが案件領域（fork の init-project で白紙化される）＝走査しない。work/・issues/ と同じ扱い。
# learnings.md は L-ID の定義元、charter.md は案件の憲章。どちらも複製で消えるので「恒久資産」ではない。
_CASE_AREA_DOCS = frozenset({"learnings.md", "charter.md"})

# 走査ルート（複製後も残る資産）。docs 直下・README・AGENTS は _durable_docs で別途集める。
_SOURCE_ROOTS = ("src/harness", "tests", "templates", ".claude/skills")
# 散文として全文走査する拡張子（.py は散文抽出に回すので含めない）。
_TEXT_SUFFIXES = frozenset({".md", ".yaml", ".yml", ".toml", ".txt", ".cfg", ".ini"})

# 免除（リポジトリ相対パス → なぜ参照してよいかの理由。空は不可）。
_EXEMPT: dict[str, str] = {
    "docs/template-copy.md": (
        "複製の手順書。前案件の `work/EP-06-…` フォルダを「消す」対象として名指しする＝一時単位への"
        "設計依存でなく、一時単位の扱いの説明なので参照が正当。"
    ),
}


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す（検証は lintkit.exempt に集約）。"""
    return validate_exemptions("doc_source_lint", _EXEMPT)


def _durable_docs(root: Path, exempt: dict[str, str]) -> list[Path]:
    """恒久の読み手向けドキュメント（README・AGENTS・docs 直下の *.md）。免除ファイルは除く。無いものは飛ばす。"""
    docs: list[Path] = []
    for rel in ("README.md", "AGENTS.md"):
        p = root / rel
        if p.is_file() and p.relative_to(root).as_posix() not in exempt:
            docs.append(p)
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        docs.extend(
            p
            for p in sorted(docs_dir.glob("*.md"))
            if p.relative_to(root).as_posix() not in exempt
            # 案件領域（fork の init-project で白紙化される）は走査しない＝work/・issues/ と同じ扱い：
            # learnings.md は L-ID の定義元、charter.md は案件の憲章で、どちらも自分の作業単位・課題・気づきを
            # 参照するのは正当（案件内の相互参照）。恒久資産ではないので「複製で宙に浮く」対象でない。
            and p.name not in _CASE_AREA_DOCS
        )
    return docs


def _source_files(root: Path, exempt: dict[str, str]) -> list[Path]:
    """複製後も残る基盤資産のファイル（.py と散文ファイル）。免除は除く。存在するルートだけ辿る。"""
    files: list[Path] = []
    for rel_root in _SOURCE_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix != ".py" and p.suffix not in _TEXT_SUFFIXES:
                continue
            if p.relative_to(root).as_posix() in exempt:
                continue
            files.append(p)
    return files


def _py_prose_chunks(src: str) -> list[tuple[int, str]]:
    """.py の散文を (行番号, 走査するテキスト) の列で返す。

    設計の根拠を書くのは人向けの散文（コメント・docstring）。文字列リテラル（関数引数・アサーション＝
    テストの合成データ）は含めない。コメントは**コメント本文だけ**を走査する（`assert "…ISS-<番号>…"  # 説明`
    のように、コード側のデータ文字列と同居する行で行全体を拾わないため）。docstring はコード非混在の純散文
    領域なので、その行範囲の原文行を走査する。構文が壊れたファイルは空（doclint と同じく構文検査の代役をしない）。
    """
    chunks: list[tuple[int, str]] = []
    # コメント：コメント本文（`#…`）だけを、その開始行で走査する。
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                chunks.append((tok.start[0], tok.string))
    except tokenize.TokenError, IndentationError, SyntaxError:
        return []
    # docstring：Module/Class/Function の先頭が文字列定数のとき、その行範囲の原文行。
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            end = first.value.end_lineno or first.value.lineno
            for lineno in range(first.value.lineno, end + 1):
                if 1 <= lineno <= len(lines):
                    chunks.append((lineno, lines[lineno - 1]))
    return chunks


def _refs_in_line(line: str) -> list[str]:
    """1 行から禁止参照（work/ パス・ISS ID・気づき ID）を集める。プレースホルダ型録表記は除く。"""
    found: list[str] = [m.group(0) for m in _WORK_REF_RE.finditer(line)]
    for m in _ISS_REF_RE.finditer(line):
        ref = m.group(0)
        if not _PLACEHOLDER_RE.search(ref):
            found.append(ref)
    found.extend(m.group(0) for m in _LEARNING_REF_RE.finditer(line))
    return found


def _problem(rel: str, lineno: int, ref: str) -> pm.Problem:
    if _LEARNING_REF_RE.fullmatch(ref):
        return pm.Problem(
            "error",
            f"{rel}:{lineno}: 複製後も残る資産が案件領域の気づき ID '{ref}' を設計の根拠に参照している。"
            f"`docs/learnings.md` の L-### は案件ごとに白紙化される（fork で消える）ので、根拠は本文の 1 文で"
            f"自足させること（『{ref} の教訓』→ その気づきが何だったのかを 1 文で書く。恒久に残したい先例は"
            f"`docs/method.md` 等の本体領域へ書き写す）。定義元の learnings.md 自身は対象外（doc_source_lint）",
        )
    return pm.Problem(
        "error",
        f"{rel}:{lineno}: 複製後も残る資産が一時的な単位 '{ref}' を設計の根拠に参照している。"
        f"`work/` の作業単位・`issues/` の課題は複製で消える／置き換わるので、根拠は本文の説明に置くこと"
        f"（例：『ISS-<番号> の対処』→ その課題が何だったのかを 1 文で書く）。"
        f"複製手順の説明なら docs/template-copy.md に書く（doc_source_lint）",
    )


def _scan_full_text(path: Path, root: Path) -> list[pm.Problem]:
    """散文ファイル（.md 等）を全文で行走査する。"""
    rel = path.relative_to(root).as_posix()
    problems: list[pm.Problem] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        problems.extend(_problem(rel, lineno, ref) for ref in _refs_in_line(line))
    return problems


def _scan_python_prose(path: Path, root: Path) -> list[pm.Problem]:
    """.py はコメント本文＋docstring だけを走査する（文字列リテラルのデータは対象外）。"""
    rel = path.relative_to(root).as_posix()
    src = path.read_text(encoding="utf-8")
    problems: list[pm.Problem] = []
    for lineno, text in _py_prose_chunks(src):
        problems.extend(_problem(rel, lineno, ref) for ref in _refs_in_line(text))
    return problems


def run_checks(root: Path) -> list[pm.Problem]:
    """複製後も残る資産が `work/` の作業単位・`issues/` の課題を設計の根拠に参照していないか検査する。参照＝error。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    for path in _durable_docs(root, exempt):
        problems.extend(_scan_full_text(path, root))
    for path in _source_files(root, exempt):
        if path.suffix == ".py":
            problems.extend(_scan_python_prose(path, root))
        else:
            problems.extend(_scan_full_text(path, root))
    return problems
