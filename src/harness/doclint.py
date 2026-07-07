"""正本ドキュメントの参照実在検査（doclint）。

AGENTS.md・CLAUDE.md・docs/method.md・docs/learnings.md・docs/template-copy.md・.claude/skills/**/*.md
が持つ参照（ISS-XXXX・相対パス・`uv run <サブコマンド>`）の実在を検査する。
対象が消える／改名されると黙って死にリンクになる問題（ISS-0003）を機械で止める。core の検査（プロファイル非依存）。
stdlib のみに依存。

方針（保守的抽出＝過検出より取りこぼしを許容）:
- パスは `docs/`・`src/`・`work/`・`tests/`・`.claude/` で始まる語だけ拾う。
- 拡張子を持つ（最終セグメントに「.」がある）か、末尾が「/」（ディレクトリ参照）のものだけ判定する。
  どちらでもない（拡張子なし・スラッシュ終端なし）ものは判定に迷う参照として拾わない。
- glob・プレースホルダ（`*`・`{`・`<` や `XXXX`・`0000` 等の型録表記）は拾わない。`*`/`{`/`<` は文字クラスで
  自然に切れるうえ、直後がこれらの文字なら途中で切れた断片とみなして捨てる。末尾の句読点（。、）や
  バッククォート・括弧は文字クラス外なので混入しない。
- 既知の `uv run` サブコマンドは pyproject.toml の [project.scripts] と .venv/bin の実行ファイル名から導出する
  （uv run はどちらも起動できるため）。導出できない環境（テスト用の一時プロジェクト等）でも動くよう、
  固定の最小集合 {"verify", "status", "task-lint", "data"} を常に含める。下位コマンド
  （`uv run data blocks` 等）は先頭の 1 語だけを確認する。未知のコマンドは info（error にしない）。
- コードフェンス（```）内も走査する＝**ドキュメント中の例に書いたパスも実在すべき**という割り切り
  （例が古びて死にリンクになるのも正本ドリフト）。例示にダミーパスを使いたいときはプレースホルダ表記
  （XXXX・xxxx・0000 や `<...>`）にすること。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from harness import issues, pm

# 固定の対象（存在するものだけ読む）。glob の対象は _target_files を参照。
_FIXED_FILES = ("AGENTS.md", "CLAUDE.md", "docs/method.md", "docs/learnings.md", "docs/template-copy.md")

_ISS_RE = re.compile(r"\bISS-\d+\b")
# 相対パス：既知の先頭ディレクトリで始まり、パスに使う文字だけが続く語。直前がパスの一部なら拾わない。
_PATH_RE = re.compile(r"(?<![\w./-])((?:docs|src|work|tests|templates|\.claude)/[\w./-]*[\w/])")
_CMD_RE = re.compile(r"\buv run ([A-Za-z0-9][\w-]*)")
# pyproject / .venv から導出できないときも常に含める最小集合（中核 CLI）。
_FALLBACK_COMMANDS = frozenset({"verify", "status", "task-lint", "data"})
# この文字が直後に続く一致は、glob・プレースホルダの途中で切れた断片なので捨てる。
_GLOBBY = "*{<"
# 型録表記（例 ISS-0000 の説明用連番）を含むパスはプレースホルダとみなして拾わない。
_PLACEHOLDER_RE = re.compile(r"XXXX|0000", re.IGNORECASE)


def _target_files(root: Path) -> list[Path]:
    """検査対象のファイル。存在するものだけ（無ければそのまま skip）。"""
    out = [p for rel in _FIXED_FILES if (p := root / rel).is_file()]
    skills = root / ".claude" / "skills"
    if skills.is_dir():
        out.extend(sorted(skills.rglob("*.md")))
    return out


def _known_commands(root: Path) -> set[str]:
    """既知の `uv run` サブコマンド。[project.scripts] と .venv/bin から導出し、最小集合を常に足す。"""
    known = set(_FALLBACK_COMMANDS)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        known.update(data.get("project", {}).get("scripts", {}))
    venv_bin = root / ".venv" / "bin"
    if venv_bin.is_dir():
        known.update(p.name for p in venv_bin.iterdir())
    return known


def _ref_file_exists(directory: Path, ref: str) -> bool:
    """ID 参照（ISS-0001 等）の実体＝その番号で始まる .md がその置き場に在るか。"""
    if not directory.is_dir():
        return False
    return any(p.name == f"{ref}.md" or p.name.startswith(f"{ref}-") for p in directory.glob(f"{ref}*.md"))


def _path_refs(text: str) -> set[str]:
    """本文から相対パス参照を保守的に抽出する（方針はモジュール docstring）。"""
    out: set[str] = set()
    for m in _PATH_RE.finditer(text):
        ref = m.group(1)
        end = m.end(1)
        if end < len(text) and text[end] in _GLOBBY:
            continue  # glob・プレースホルダの断片
        if _PLACEHOLDER_RE.search(ref):
            continue  # 型録表記（XXXX・0000 連番）はパスとして判定しない
        if ref.endswith("/") or "." in ref.rsplit("/", 1)[-1]:
            out.add(ref)
        # 拡張子もスラッシュ終端も無い語は迷う参照＝拾わない。
    return out


def run_checks(root: Path) -> list[pm.Problem]:
    """正本ドキュメントの参照実在検査。死にリンク＝error、未知コマンド＝warn。"""
    problems: list[pm.Problem] = []
    iss_dir = issues.local_dir(root)  # github: backend のときは None＝ISS 検査を行わない
    known_commands = _known_commands(root)

    for path in _target_files(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")

        if iss_dir is not None:
            iss_rel = iss_dir.relative_to(root).as_posix()
            for ref in sorted(set(_ISS_RE.findall(text))):
                if not _ref_file_exists(iss_dir, ref):
                    problems.append(pm.Problem("error", f"{rel}: '{ref}' の課題（{iss_rel}/{ref}-*.md）が見つからない"))

        for ref in sorted(_path_refs(text)):
            target = root / ref
            if ref.endswith("/"):
                if not target.is_dir():
                    problems.append(pm.Problem("error", f"{rel}: 参照先のディレクトリ '{ref}' が存在しない"))
            elif not target.exists():
                problems.append(pm.Problem("error", f"{rel}: 参照先のパス '{ref}' が存在しない"))

        for name in sorted(set(_CMD_RE.findall(text))):
            if name not in known_commands:
                # 死にリンク（ISS/パス）は error、未知コマンドは info（pm.Problem の "error"|"info" 規約に沿う。
                # コマンド既知集合は環境（.venv）由来で偽陽性がありうるため合否には効かせない）。
                problems.append(pm.Problem("info", f"{rel}: 'uv run {name}' が既知のコマンドに無い（タイポの可能性）"))

    return problems
