"""正本ドキュメントの参照実在検査（doclint）。

AGENTS.md・CLAUDE.md・docs/core.md・docs/method.md・docs/learnings.md・docs/template-copy.md・
.claude/skills/**/*.md が持つ参照（ID 参照・相対パス・`uv run <サブコマンド>`）の実在を検査する。
対象が消える／改名されると、正本ドキュメントの参照が黙って死にリンクになる。それを機械で止める。
core の検査（プロファイル非依存）。
stdlib のみに依存。

方針（保守的抽出＝過検出より取りこぼしを許容）:
- パスは `docs/`・`src/`・`work/`・`tests/`・`.claude/` で始まる語だけ拾う。
- 拡張子を持つ（最終セグメントに「.」がある）か、末尾が「/」（ディレクトリ参照）のものは実体の有無をそのまま
  判定する。どちらでもない（拡張子なし・スラッシュ終端なし）ものは、先頭 2 セグメントがディレクトリとして
  実在するかだけを見る（T-0165：`docs/decisions/DEC-xxxx` のような、仕組みを撤去した後の参照が
  「判定に迷う」扱いのまま素通りしていた穴を塞ぐ）。ただし拡張子・末尾スラッシュという「パスである強い
  手掛かり」を持たない候補は、全体が ASCII のパス構成文字（`[A-Za-z0-9._/-]`）のものだけを検査する
  （`_PATH_RE` の `\\w` は Unicode を含み、日本語の散文の一部がパスに見えてしまうため）。
- glob・プレースホルダ（`*`・`{`・`<`・`…` や `XXXX`・`0000` 等の型録表記）は拾わない。`*`/`{`/`<`/`…` は文字クラスで
  自然に切れるうえ、直後（またはハイフン 1 つを挟んだ次）がこれらの文字なら途中で切れた断片とみなして捨てる。
  末尾の句読点（。、）やバッククォート・括弧は文字クラス外なので混入しない。
- 既知の `uv run` サブコマンドは pyproject.toml の [project.scripts] と .venv の実行ファイル名（bin/ か
  Windows の Scripts/、拡張子を除いた stem）から導出する（uv run はどちらも起動できるため）。導出できない
  環境（テスト用の一時プロジェクト等）でも動くよう、固定の最小集合 {"verify", "status", "task-lint", "data"}
  を常に含める。下位コマンド（`uv run data blocks` 等）は先頭の 1 語だけを確認する。未知のコマンドは info
  （error にしない）。
- コードフェンス（```）内も走査する＝**ドキュメント中の例に書いたパスも実在すべき**という割り切り
  （例が古びて死にリンクになるのも正本ドリフト）。例示にダミーパスを使いたいときはプレースホルダ表記
  （XXXX・xxxx・0000 や `<...>`・`…`）にすること。

ID 参照の実在検査（`ISS-<番号>` 等）:
- 接頭辞ごとに置き場ディレクトリを持つ（`_ID_HOMES`。ISS だけは `.harness/config.toml` の
  `issues.backend` で決まるので実行時に解決する＝github: backend なら検査しない）。
- 置き場ディレクトリ自体が存在しない接頭辞への参照は、実体の有無に関わらずすべて error にする
  （T-0165：`docs/decisions/` を撤去した後も `DEC-xxxx` 参照が 8 箇所残っていた＝仕組みを撤去したのに
  参照が残っている状態を、ISS 専用だった旧実装は検出できなかった）。
- 走査対象は上記の対象文書に加え、`src/**/*.py` の文字列リテラル（`ast` で抽出。コメントは対象外）。
  エラーメッセージ・docstring は読み手向けの文書であり、撤去済みの仕組みを指す実例が実際にあったため
  （`src/harness/doc_source_lint.py` の旧エラーメッセージ）。パス参照（拡張子/ディレクトリ/先頭 2
  セグメント）の検査は対象文書のみに留める＝ソースコードは識別子・正規表現の断片を含み、パスらしき
  文字列が地の文にも頻出するため過検出の的（ID 参照はハイフン＋数字という強い形があるので誤検出が少ない）。
"""

from __future__ import annotations

import ast
import fnmatch
import re
import tomllib
from pathlib import Path

from harness import issues, pm
from harness.init_project import CASE_AREA_ROOTS


def _is_case_area(ref: str) -> bool:
    """ref が案件領域（init-project が白紙化する per-project の置き場・正本は init_project.CASE_AREA_ROOTS）に属するか。

    そこに在るべきファイル（例 `docs/wbs.yaml`）は fresh clone に無くて当然なので、durable な docs がそれを
    指しても壊れリンクではない＝実在検査から除外する（案件領域外の不在パスは従来どおり error のまま）。
    """
    normalized = ref.rstrip("/")
    for root in CASE_AREA_ROOTS:
        base = root.rstrip("/")
        if normalized == base or normalized.startswith(base + "/") or fnmatch.fnmatch(normalized, base):
            return True
    return False


# 固定の対象（存在するものだけ読む）。glob の対象は _target_files を参照。
_FIXED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/core.md",
    "docs/method.md",
    "docs/learnings.md",
    "docs/template-copy.md",
)

# 相対パス：既知の先頭ディレクトリで始まり、パスに使う文字だけが続く語。直前がパスの一部なら拾わない。
_PATH_RE = re.compile(r"(?<![\w./-])((?:docs|src|work|tests|templates|\.claude)/[\w./-]*[\w/])")
_CMD_RE = re.compile(r"\buv run ([A-Za-z0-9][\w-]*)")
# pyproject / .venv から導出できないときも常に含める最小集合（中核 CLI）。
_FALLBACK_COMMANDS = frozenset({"verify", "status", "task-lint", "data"})
# この文字が直後に続く一致は、glob・プレースホルダの途中で切れた断片なので捨てる。
_GLOBBY = "*{<…"
# 型録表記（例 ISS-0000 の説明用連番）を含むパスはプレースホルダとみなして拾わない。
_PLACEHOLDER_RE = re.compile(r"XXXX|0000", re.IGNORECASE)
# 拡張子もスラッシュ終端も持たないパス候補は、全体が ASCII のパス構成文字だけのときに限り検査する。
# _PATH_RE の `\w` は Unicode を含む（日本語の散文の一部がパスに見えてしまう）ため、拡張子や末尾スラッシュ
# という「パスである強い手掛かり」を持たない候補は、非 ASCII を含む＝散文とみなして拾わない（T-0165）。
_ASCII_PATH_RE = re.compile(r"[A-Za-z0-9._/-]+")

# ID 接頭辞 → 置き場ディレクトリ（root からの相対パス）。ISS は config（issues.backend）で決まるので
# ここには含めず、_id_homes() で実行時に解決する。
_ID_HOMES: dict[str, str] = {
    "REQ": "docs/requirements",
    "DEC": "docs/decisions",
}
_ID_PREFIXES = ("ISS", *_ID_HOMES)
_ID_REF_RE = re.compile(rf"\b({'|'.join(_ID_PREFIXES)})-(\d+)\b")


def _target_files(root: Path) -> list[Path]:
    """検査対象のファイル。存在するものだけ（無ければそのまま skip）。"""
    out = [p for rel in _FIXED_FILES if (p := root / rel).is_file()]
    skills = root / ".claude" / "skills"
    if skills.is_dir():
        out.extend(sorted(skills.rglob("*.md")))
    return out


def _python_string_literals(root: Path) -> list[tuple[Path, str]]:
    """src/**/*.py の文字列リテラル（docstring・f-string の固定部分含む。コメントは対象外）を ast で集める。

    ファイルごとに 1 本のテキストへ結合して返す。構文が壊れたファイルは飛ばす（doclint は構文検査の代役をしない）。
    """
    out: list[tuple[Path, str]] = []
    src_dir = root / "src"
    if not src_dir.is_dir():
        return out
    for path in sorted(src_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if literals:
            out.append((path, "\n".join(literals)))
    return out


def _known_commands(root: Path) -> set[str]:
    """既知の `uv run` サブコマンド。[project.scripts] と .venv の実行ファイルから導出し、最小集合を常に足す。"""
    known = set(_FALLBACK_COMMANDS)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        known.update(data.get("project", {}).get("scripts", {}))
    # Windows の venv は Scripts/（実行ファイルは pytest.exe のように拡張子付き）。posix は bin/。
    # p.stem で拡張子を落として登録する（bin 側は元々拡張子が無いので stem == name のまま）。
    for sub in ("bin", "Scripts"):
        venv_dir = root / ".venv" / sub
        if venv_dir.is_dir():
            known.update(p.stem for p in venv_dir.iterdir())
    return known


def _id_homes(root: Path) -> dict[str, Path | None]:
    """接頭辞ごとの置き場（絶対パス）。ISS は config 次第で None（github backend＝検査しない）。"""
    homes: dict[str, Path | None] = {prefix: root / rel for prefix, rel in _ID_HOMES.items()}
    homes["ISS"] = issues.local_dir(root)
    return homes


def _ref_file_exists(directory: Path, ref: str) -> bool:
    """ID 参照（`ISS-<番号>` 等）の実体＝その番号で始まる .md がその置き場に在るか。"""
    if not directory.is_dir():
        return False
    return any(p.name == f"{ref}.md" or p.name.startswith(f"{ref}-") for p in directory.glob(f"{ref}*.md"))


def _all_path_matches(text: str) -> list[str]:
    """本文からパスらしき語を保守的に抽出する（glob・プレースホルダは除く。分類前の生のリスト）。"""
    out: list[str] = []
    for m in _PATH_RE.finditer(text):
        ref = m.group(1)
        end = m.end(1)
        nxt = text[end] if end < len(text) else ""
        if nxt in _GLOBBY:
            continue  # glob・プレースホルダの断片
        # ハイフン 1 つを挟んで glob・プレースホルダが続く（`work/EP-<番号>`・`docs/x-*.md` 等）のも断片。
        if nxt == "-" and end + 1 < len(text) and text[end + 1] in _GLOBBY:
            continue
        if _PLACEHOLDER_RE.search(ref):
            continue  # 型録表記（XXXX・0000 連番）はパスとして判定しない
        out.append(ref)
    return out


def _path_refs(text: str) -> set[str]:
    """拡張子ありかディレクトリ参照（末尾スラッシュ）＝実体の有無をそのまま判定できる参照。"""
    return {ref for ref in _all_path_matches(text) if ref.endswith("/") or "." in ref.rsplit("/", 1)[-1]}


def _bare_path_refs(text: str) -> set[str]:
    """拡張子もスラッシュ終端も無い参照＝先頭 2 セグメントの実在だけで判定する（T-0165）。

    パスである強い手掛かり（拡張子・末尾スラッシュ）が無いので、非 ASCII を含む候補は日本語の散文が
    `\\w` に拾われた誤検出とみなして除外する（全体が ASCII のパス構成文字のものだけ検査する）。
    """
    return {
        ref
        for ref in _all_path_matches(text)
        if not (ref.endswith("/") or "." in ref.rsplit("/", 1)[-1]) and _ASCII_PATH_RE.fullmatch(ref) is not None
    }


def _id_ref_problems(rel: str, text: str, homes: dict[str, Path | None], root: Path) -> list[pm.Problem]:
    """ID 参照（`ISS-<番号>` 等）の実在を、接頭辞ごとの置き場（homes）で検査する。

    置き場が None（ISS の github backend）は検査しない。置き場ディレクトリ自体が無ければ、
    その接頭辞への参照はすべて error（仕組みを撤去したのに参照が残っている状態を検出する）。
    """
    problems: list[pm.Problem] = []
    for prefix, num in sorted(set(_ID_REF_RE.findall(text))):
        ref = f"{prefix}-{num}"
        home = homes.get(prefix)
        if home is None:
            continue
        home_rel = home.relative_to(root).as_posix()
        if not home.is_dir():
            problems.append(
                pm.Problem("error", f"{rel}: '{ref}' の置き場 '{home_rel}' が存在しない（仕組みが撤去された可能性）")
            )
        elif not _ref_file_exists(home, ref):
            problems.append(pm.Problem("error", f"{rel}: '{ref}' の実体（{home_rel}/{ref}-*.md）が見つからない"))
    return problems


def _path_ref_problems(rel: str, text: str, root: Path) -> list[pm.Problem]:
    """相対パス参照の実在検査（拡張子/ディレクトリ参照＝そのまま判定、それ以外＝先頭 2 セグメントだけ判定）。"""
    problems: list[pm.Problem] = []
    for ref in sorted(_path_refs(text)):
        if _is_case_area(ref):
            continue  # 案件領域（fresh clone で白紙化される per-project の置き場）は不在を咎めない
        target = root / ref
        if ref.endswith("/"):
            if not target.is_dir():
                problems.append(pm.Problem("error", f"{rel}: 参照先のディレクトリ '{ref}' が存在しない"))
        elif not target.exists():
            problems.append(pm.Problem("error", f"{rel}: 参照先のパス '{ref}' が存在しない"))
    for ref in sorted(_bare_path_refs(text)):
        if _is_case_area(ref):
            continue
        # 参照先そのものの実在は問わない（拡張子が無いので、ファイルか節の見出しか判別できない）。
        # 「参照先を含むディレクトリが存在するか」だけを見る＝撤去された仕組み（docs/decisions/…）を捕まえ、
        # 拡張子を省いたファイル参照（tests/conftest）は誤検出しない。
        parent = "/".join(ref.split("/")[:-1])
        if not (root / parent).is_dir():
            problems.append(pm.Problem("error", f"{rel}: 参照先 '{ref}' の置き場 '{parent}' が存在しない"))
    return problems


def _command_ref_problems(rel: str, text: str, known_commands: set[str]) -> list[pm.Problem]:
    """`uv run <サブコマンド>` の既知チェック。未知は info（タイポの可能性・合否には効かせない）。"""
    problems: list[pm.Problem] = []
    for name in sorted(set(_CMD_RE.findall(text))):
        if name not in known_commands:
            problems.append(pm.Problem("info", f"{rel}: 'uv run {name}' が既知のコマンドに無い（タイポの可能性）"))
    return problems


def run_checks(root: Path) -> list[pm.Problem]:
    """正本ドキュメントの参照（ID・パス・`uv run` コマンド）の実在検査。死にリンク＝error、未知コマンド＝info。"""
    problems: list[pm.Problem] = []
    homes = _id_homes(root)
    known_commands = _known_commands(root)

    for path in _target_files(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        problems.extend(_id_ref_problems(rel, text, homes, root))
        problems.extend(_path_ref_problems(rel, text, root))
        problems.extend(_command_ref_problems(rel, text, known_commands))

    # src/**/*.py の文字列リテラル：ID 参照の実在だけを見る（理由はモジュール docstring）。
    for path, text in _python_string_literals(root):
        rel = path.relative_to(root).as_posix()
        problems.extend(_id_ref_problems(rel, text, homes, root))

    return problems
