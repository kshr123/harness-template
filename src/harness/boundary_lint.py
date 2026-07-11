"""中核（`src/harness/*.py`）がプロファイルを import しないことの検査（boundary_lint）。

`docs/core.md` は「中核はプロファイル（ds・serve・agent・ops）のコードを import しない」を最重要の不変量
として宣言しているが、これまでの担保は規約 (c)（人が気をつける）だけだった。import 文という**構文の印**が
あるので (b)（機械が検出する）にできる：対象集合＝`src/harness/*.py`（直下・非再帰の中核モジュール）を
ファイルシステムから機械的に導き、各ファイルの import を ast で解析して `harness.(ds|serve|agent|ops)` への
依存を error にする。

方針（coverage_lint / code_doc_lint と同じ ast・allowlist の作法）:
- **ast で解析**する（文字列 grep ではない＝コメント・docstring 内の "import harness.ds" のような文字列に
  誤爆しない）。`ast.walk` で全ノードを見るので、**関数内の遅延 import も検出する**（トップレベルの import
  文だけを見ると、遅延 import で境界を越える抜け道が残る）。
- 相対 import（`from . import ds`・`from .ds.models import X`）も解決する。中核モジュールの親パッケージは
  `harness` なので、level>=1 はそこを起点に解決する。
- **対象は中核だけ**（`src/harness/*.py`・非再帰）。プロファイル同士の import（`serve` → `ds` 等）は別の
  境界の話なので、この検査は扱わない（対象集合を「中核が触れてよいのは中核だけ」に限定する）。
- 免除は `_EXEMPT`（(中核モジュールのファイル名, import 先モジュール) → 理由）だけ。理由必須（空は
  ValueError＝黙って免除しない。fail closed）。免除を増やす前に「なぜ中核がプロファイルを要るのか」を疑う。

core の検査（プロファイル非依存）。stdlib のみに依存。`harness.pm.Problem` を返すため `pm` を先頭で import
する。循環はしない：`pm` はこのモジュールを import せず、両者を束ねる `checks.py` が `PM_CHECKS` にこの
`run_checks` を登録して verify に載せる（他の lint と同じ作法）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from harness import pm

# プロファイルのディレクトリ名（`src/harness/<name>/`）。中核がこれらを import してはいけない。
_PROFILES = ("ds", "serve", "agent", "ops")

# 免除リスト：(中核モジュールのファイル名, import 先の完全修飾モジュール) → なぜ許すかの理由（空は不可）。
# 例：("cli.py", "harness.ds")。現状は空（中核 → プロファイルの越境は 0 件）。
_EXEMPT: dict[tuple[str, str], str] = {}


def _validated_exempt() -> dict[tuple[str, str], str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for key, reason in _EXEMPT.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{key!r}] の理由が空。免除には人が読める理由が必須（boundary_lint）")
    return _EXEMPT


def _core_modules(root: Path) -> list[Path]:
    """中核モジュール＝`src/harness/*.py`（直下・非再帰）。プロファイルの入れ子（`src/harness/ds/…`）は含めない。"""
    base = root / "src" / "harness"
    return sorted(base.glob("*.py")) if base.is_dir() else []


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


def _profile_of(module: str) -> str | None:
    """完全修飾モジュール名がプロファイルへの依存なら、そのプロファイル名を返す（そうでなければ None）。"""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "harness" and parts[1] in _PROFILES:
        return parts[1]
    return None


def _violations(path: Path) -> list[tuple[int, str, str, bool]]:
    """1 つの中核モジュールの越境を (行番号, import 先モジュール, プロファイル, 遅延か) の一覧で返す。

    `ast.walk` で全ノードを見るため、関数内の遅延 import も拾う（トップレベル body に無い import ＝遅延）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    toplevel = {id(stmt) for stmt in tree.body}
    out: list[tuple[int, str, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        for module in _imported_modules(node):
            profile = _profile_of(module)
            if profile is not None:
                out.append((node.lineno, module, profile, id(node) not in toplevel))
    return out


def run_checks(root: Path) -> list[pm.Problem]:
    """中核（src/harness/*.py）がプロファイル（ds・serve・agent・ops）を import していないか検査する。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    for path in _core_modules(root):
        filename = path.name
        for lineno, module, profile, lazy in _violations(path):
            if (filename, module) in exempt:
                continue
            kind = "遅延 import" if lazy else "import"
            problems.append(
                pm.Problem(
                    "error",
                    f"src/harness/{filename}:{lineno}: 中核がプロファイル '{profile}' を {kind} している"
                    f"（{module}）。docs/core.md の不変量『中核はプロファイルを import しない』に反する。"
                    f"プロファイル依存を中核から外すこと（真に必要なら理由つきで boundary_lint の _EXEMPT に）",
                )
            )
    return problems
