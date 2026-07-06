"""テスト規約の機械検査（conventions lint・ISS-0002）。

AGENTS のテスト規約のうち「レビュー観点」止まりだった規約を静的検査に昇格する（core・stdlib の ast のみ）。

1. **グローバル種の禁止**：`np.random.seed`・`numpy.random.seed`・`random.seed` の**呼び出し**を
   `src/`・`tests/`・`work/**/code/**/*.py`（code 配下は再帰的に）から ast で検出して error（ファイル・行を含む）。
   属性チェーンに加え `from numpy.random import seed`／`from random import seed`（別名も）で取り込んだ `seed(...)` の
   直接呼び出しも捕まえる。明示引数（`seed=`・`random_state=`）や `default_rng` は対象外（関数名が `seed` でない）。
   文字列・コメント中は ast の走査対象にならず自然に除外される（この検査自身や検査のテストも誤検出しない）。
   ※ `RandomState(0)` 等の別 API・`rng = np.random; rng.seed()` の間接束縛は保守的に見逃す（中心形は確実に捕まえる）。
2. **実験スクリプトの `--test` 必須**：`work/**/code/**/*.py` のうち argparse を使うスクリプト
   （`argparse` を import し `ArgumentParser` を参照する）に `add_argument(..., "--test", ...)`（**位置引数のどれか**が
   "--test"＝`-t` 併記でも可）が無ければ error。argparse 非使用の .py（部品モジュール等）は対象外＝実行入口だけ。
   src/・tests/ の argparse CLI にはこの規約を課さない。
3. **命令形 skip の ISS 参照必須**：テスト本体で呼ぶ `pytest.skip(...)`／`pytest.xfail(...)` は理由に `ISS-\\d+` が
   無ければ error（マーカー版はそこを素通りするので補完）。`pytest.importorskip(...)` は optional 依存の入口＝対象外。

マーカー版 skip/xfail の ISS 参照は tests/conftest.py の収集フック＋harness.testing.skips_without_iss が担う。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from harness import pm

# グローバル種の呼び出しとみなす属性チェーン（np/numpy/random 起点の ...seed だけ＝保守的）。
_GLOBAL_SEED_CALLS = frozenset({"np.random.seed", "numpy.random.seed", "random.seed"})
# from-import で seed を取り込みうるモジュール（この seed の直接呼び出しもグローバル種）。
_SEED_IMPORT_MODULES = frozenset({"numpy.random", "random"})
_ISS_REF = re.compile(r"ISS-\d+")
_IMPERATIVE_SKIPS = frozenset({"pytest.skip", "pytest.xfail"})  # importorskip は optional 依存の入口＝対象外


def _target_files(root: Path) -> list[tuple[Path, bool]]:
    """検査対象の .py の一覧。(path, work の code か) を返す（--test 規約は work の code だけに課す）。"""
    out: list[tuple[Path, bool]] = []
    for top in ("src", "tests"):
        directory = root / top
        if directory.is_dir():
            out.extend((p, False) for p in sorted(directory.rglob("*.py")))
    work = root / "work"
    if work.is_dir():
        # work/**/code 配下は再帰的に（code/pkg/mod.py 等でグローバル種を逃さない）。
        out.extend((p, True) for p in sorted(work.rglob("*.py")) if "code" in p.relative_to(work).parts)
    return out


def _dotted_name(node: ast.expr) -> str | None:
    """`np.random.seed` のような Name 起点の属性チェーンをドット区切り文字列にする（それ以外は None）。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _seed_local_names(tree: ast.AST) -> set[str]:
    """`from numpy.random import seed [as x]`／`from random import seed` で束ねた局所名の集合。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _SEED_IMPORT_MODULES:
            names.update(alias.asname or alias.name for alias in node.names if alias.name == "seed")
    return names


def _global_seed_lines(tree: ast.AST) -> list[int]:
    """グローバル種の呼び出し（属性チェーン一致 or from-import した seed の直接呼び出し）の行番号。"""
    seed_names = _seed_local_names(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted_name(node.func)
        if dotted in _GLOBAL_SEED_CALLS:
            lines.append(node.lineno)
        elif isinstance(node.func, ast.Name) and node.func.id in seed_names:  # from-import した seed(...) 呼び出し
            lines.append(node.lineno)
    return sorted(lines)


def _uses_argparse(tree: ast.AST) -> bool:
    """argparse を import し、ArgumentParser を呼んでいるか（＝コマンドラインの実行入口とみなす）。"""
    imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "argparse" for alias in node.names):
            imported = True
        elif isinstance(node, ast.ImportFrom) and node.module == "argparse":
            imported = True
    if not imported:
        return False
    return any(
        isinstance(node, ast.Call) and _dotted_name(node.func) in ("argparse.ArgumentParser", "ArgumentParser")
        for node in ast.walk(tree)
    )


def _has_test_flag(tree: ast.AST) -> bool:
    """`add_argument(..., "--test", ...)`（**位置引数のどれか**が "--test"＝`-t` 併記でも可）が在るか。"""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and any(isinstance(a, ast.Constant) and a.value == "--test" for a in node.args)
        ):
            return True
    return False


def _imperative_skip_lines_without_iss(tree: ast.AST) -> list[int]:
    """`pytest.skip(...)`／`pytest.xfail(...)` の呼び出しで理由に ISS 参照が無いものの行番号。"""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _dotted_name(node.func) in _IMPERATIVE_SKIPS):
            continue
        reasons: list[str] = [str(a.value) for a in node.args if isinstance(a, ast.Constant)]
        reasons += [
            str(kw.value.value) for kw in node.keywords if kw.arg == "reason" and isinstance(kw.value, ast.Constant)
        ]
        if not any(_ISS_REF.search(r) for r in reasons):
            lines.append(node.lineno)
    return sorted(lines)


def run_checks(root: Path) -> list[pm.Problem]:
    """テスト規約の静的検査。グローバル種・--test 欠落・ISS 無し命令形 skip＝error、構文解析できないファイル＝info。"""
    problems: list[pm.Problem] = []
    for path, is_work_code in _target_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            # 構文の壊れは ruff/pytest が別途止める。ここでは合否に効かせず知らせるだけ（偽陽性を出さない）。
            problems.append(pm.Problem("info", f"{rel}: 構文解析できないため規約検査を飛ばした（{exc.msg}）"))
            continue
        for lineno in _global_seed_lines(tree):
            problems.append(
                pm.Problem(
                    "error",
                    f"{rel}:{lineno}: グローバル種の呼び出し（np.random.seed 等）は禁止＝乱数は明示引数（seed=）で渡す",
                )
            )
        for lineno in _imperative_skip_lines_without_iss(tree):
            problems.append(
                pm.Problem(
                    "error",
                    f"{rel}:{lineno}: pytest.skip/xfail は理由に ISS 参照（ISS-1234）が必須（なぜ止め いつ戻すか）",
                )
            )
        if is_work_code and _uses_argparse(tree) and not _has_test_flag(tree):
            problems.append(
                pm.Problem(
                    "error",
                    f'{rel}: 実験スクリプトに --test（スモーク）引数が無い（add_argument("--test", ...) を足す）',
                )
            )
    return problems
