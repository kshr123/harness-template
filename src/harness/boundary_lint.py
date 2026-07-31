"""中核（`src/harness/*.py`）がプロファイルを import しないことの検査（boundary_lint）。

`docs/core.md` は「中核はプロファイル（ds・serve・agent・ops）のコードを import しない」を最重要の不変量
として宣言しているが、これまでの担保は規約 (c)（人が気をつける）だけだった。import 文という**構文の印**が
あるので (b)（機械が検出する）にできる：対象集合＝`src/harness/**/*.py` のうちプロファイル（`profile.py` を
持つディレクトリ配下）を除いた中核（直下＋中核サブパッケージ `lintkit/` 等）を機械的に導き、各ファイルの
import を ast で解析して `harness.(ds|serve|agent|ops)` への依存を error にする。

方針（coverage_lint / code_doc_lint と同じ ast・allowlist の作法）:
- **ast で解析**する（文字列 grep ではない＝コメント・docstring 内の "import harness.ds" のような文字列に
  誤爆しない）。`ast.walk` で全ノードを見るので、**関数内の遅延 import も検出する**（トップレベルの import
  文だけを見ると、遅延 import で境界を越える抜け道が残る）。
- 相対 import（`from . import ds`・`from .ds.models import X`）も解決する。中核モジュールの親パッケージは
  `harness` なので、level>=1 はそこを起点に解決する。
- **対象は中核だけ**（`src/harness/**/*.py` から profile.py を持つディレクトリ配下を除く＝直下＋中核
  サブパッケージ）。プロファイル同士の import（`serve` → `ds` 等）は別の境界の話なので扱わない（対象集合を
  「中核が触れてよいのは中核だけ」に限定する）。
- 免除は `_EXEMPT`（(中核モジュールのファイル名, import 先モジュール) → 理由）だけ。理由必須（空は
  ValueError＝黙って免除しない。fail closed）。免除を増やす前に「なぜ中核がプロファイルを要るのか」を疑う。

core の検査（プロファイル非依存）。stdlib のみに依存。`harness.pm.Problem` を返すため `pm` を先頭で import
する。循環はしない：`pm` はこのモジュールを import せず、両者を束ねる `checks.py` が `INVARIANT_CHECKS` にこの
`run_checks` を登録して verify に載せる（他の lint と同じ作法）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from harness import pm, profiles
from harness.lintkit.exempt import validate_exemptions

# 免除リスト：(中核モジュールの src/harness からの相対パス, import 先の完全修飾モジュール) → 理由（空は不可）。
# 直下は "cli.py"、サブパッケージは "lintkit/corpus.py"。例：("cli.py", "harness.ds")。現状は空（越境 0 件）。
_EXEMPT: dict[tuple[str, str], str] = {}


def _validated_exempt() -> dict[tuple[str, str], str]:
    """免除リストの理由が空でないことを確かめて返す（検証は lintkit.exempt に集約）。"""
    return validate_exemptions("boundary_lint", _EXEMPT)


def _core_modules(root: Path) -> list[Path]:
    """中核モジュール＝`src/harness/**/*.py` のうち、プロファイル（`profile.py` を持つディレクトリ配下）を除く。

    直下だけでなく中核の下位パッケージ（例 `src/harness/lintkit/`）も対象にする＝新しい中核サブパッケージが
    境界検査から漏れない（対象集合を「profile.py を持つディレクトリだけ外す」で機械的に導く＝(b) の作法。
    直下だけを見ると、サブパッケージ内の `import harness.ds` が黙って通る死角になる）。
    """
    base = root / "src" / "harness"
    if not base.is_dir():
        return []
    profile_dirs = [p.parent for p in base.glob("*/profile.py")]
    return sorted(p for p in base.rglob("*.py") if not any(pd in p.parents for pd in profile_dirs))


def _package_of(path: Path, base: Path) -> str:
    """中核ファイルの所属パッケージ（相対 import の起点）。`src/harness/x.py`→`harness`、
    `src/harness/lintkit/x.py`→`harness.lintkit`。サブパッケージ内の相対 import を正しく解決するために要る。"""
    parts = path.relative_to(base).parts[:-1]  # ファイル名を除いたディレクトリ部分
    return ".".join(("harness", *parts))


def _imported_modules(node: ast.Import | ast.ImportFrom, pkg: str = "harness") -> list[str]:
    """import 文が参照する完全修飾モジュール名の一覧を返す（相対 import も `pkg` を起点に解決する）。

    - `import harness.ds.models` → ["harness.ds.models"]
    - `from harness.ds import models` → ["harness.ds"]（module 部分だけを見る＝プロファイルの判定には十分）
    - `from . import ds`（level 1・`pkg=harness`）→ ["harness.ds"]
    - `from .ds.models import X`（level 1）→ ["harness.ds.models"]
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    # ImportFrom
    if node.level == 0:
        return [node.module] if node.module else []
    base_parts = pkg.split(".")
    up = node.level - 1  # level 1 = pkg 自身、level 2 = その親…
    base = base_parts[: len(base_parts) - up] if up <= len(base_parts) else []
    prefix = ".".join(base)
    if node.module:
        return [f"{prefix}.{node.module}" if prefix else node.module]
    return [f"{prefix}.{alias.name}" if prefix else alias.name for alias in node.names]


def _profile_of(module: str, profile_names: frozenset[str]) -> str | None:
    """完全修飾モジュール名がプロファイルへの依存なら、そのプロファイル名を返す（そうでなければ None）。

    プロファイルの集合は手書きせず `profiles.profile_names`（`src/harness/<name>/profile.py` の走査）から
    渡す＝新しいプロファイルを足しても境界検査が自動で覆う（一覧の二重管理をしない）。
    """
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "harness" and parts[1] in profile_names:
        return parts[1]
    return None


def _violations(path: Path, profile_names: frozenset[str], pkg: str) -> list[tuple[int, str, str, bool]]:
    """1 つの中核モジュールの越境を (行番号, import 先モジュール, プロファイル, 遅延か) の一覧で返す。

    `ast.walk` で全ノードを見るため、関数内の遅延 import も拾う（トップレベル body に無い import ＝遅延）。
    相対 import は所属パッケージ `pkg` を起点に解決する（サブパッケージ内の `from ..ds import x` も正しく判定）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    toplevel = {id(stmt) for stmt in tree.body}
    out: list[tuple[int, str, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for module in _imported_modules(node, pkg):
            profile = _profile_of(module, profile_names)
            if profile is not None:
                out.append((node.lineno, module, profile, id(node) not in toplevel))
    return out


def run_checks(root: Path) -> list[pm.Problem]:
    """中核（src/harness/*.py）がプロファイル（ds・serve・agent…）を import していないか検査する。

    プロファイルの集合は `profiles.profile_names`（同梱の profile.py から導出）＝手書きの一覧を持たない。
    """
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    profile_names = frozenset(profiles.profile_names(root))
    base = root / "src" / "harness"
    for path in _core_modules(root):
        rel = path.relative_to(base).as_posix()  # 直下は "cli.py"・サブパッケージは "lintkit/corpus.py"
        for lineno, module, profile, lazy in _violations(path, profile_names, _package_of(path, base)):
            if (rel, module) in exempt:
                continue
            kind = "遅延 import" if lazy else "import"
            problems.append(
                pm.Problem(
                    "error",
                    f"src/harness/{rel}:{lineno}: 中核がプロファイル '{profile}' を {kind} している"
                    f"（{module}）。docs/core.md の不変量『中核はプロファイルを import しない』に反する。"
                    f"プロファイル依存を中核から外すこと（真に必要なら理由つきで boundary_lint の _EXEMPT に）",
                )
            )
    return problems
