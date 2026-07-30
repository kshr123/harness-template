"""テスト規約・ソース規約の機械検査（conventions lint）。

AGENTS のテスト規約・ソース規約のうち「レビュー観点」止まりだった規約を静的検査に昇格する（core・stdlib の ast のみ）。

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
4. **`subprocess` の文字列モードに `encoding` 必須**：`text=True`／`universal_newlines=True` を渡すのに
   `encoding=` が無い呼び出しを error。省略時はロケールの符号化方式（Windows の日本語環境では cp932）で
   復号され、UTF-8 の出力を読むと `UnicodeDecodeError` になる。ハーネスの CLI は日本語を出すため必ず踏む。
5. **リポ相対パスの文字列化は `.as_posix()` 必須**：`str(x.relative_to(y))` と f-string の `{x.relative_to(y)}` を
   error にする（`.as_posix()` を挟めば一致しない）。省略すると Windows で `\\` 区切りになり、生成物（STATUS.md 等）や
   編集セッションの指紋キーが OS で食い違う。中心の 2 形を確実に捕まえる（別名に束ねてから文字列化する形＝
   `rel = p.relative_to(r)` … `f"{rel}"` はデータフロー解析が要るので見逃す＝束ねる箇所で `.as_posix()` を呼ぶ規約は
   レビュー観点）。

マーカー版 skip/xfail の ISS 参照は tests/conftest.py の収集フック＋harness.testing.skips_without_iss が担う。
slow マーカー（`@pytest.mark.slow`／モジュール直書きの `pytestmark = pytest.mark.slow` どちらも）も同じ関数・
同じ収集フックで ISS 参照必須にする（`harness.testing.SKIP_MARKERS` に slow を含める＝T-0202）。slow には
呼び出し形（`pytest.slow(...)`）が存在しないため、この静的検査（conventions.py）には対応する枝を足さない。
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
# 子プロセスの出力を文字列で受け取りうる呼び出し（bytes のまま扱う形は対象外＝復号が起きない）。
_SUBPROCESS_CALLS = frozenset(
    {"subprocess.run", "subprocess.check_output", "subprocess.Popen", "subprocess.call", "subprocess.check_call"}
)
# 文字列モードに切り替える引数（どちらも同義。真のときだけロケール既定の復号が起きる）。
_TEXT_MODE_KEYWORDS = ("text", "universal_newlines")


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


def _subprocess_text_without_encoding_lines(tree: ast.AST) -> list[int]:
    """文字列モード（text／universal_newlines が真）なのに `encoding=` を渡さない subprocess 呼び出しの行番号。

    `encoding` 省略時は `locale.getencoding()` で復号される。Windows の日本語環境では cp932 になり、
    UTF-8 で書かれた子プロセスの出力（ハーネスの CLI は日本語）を読むと `UnicodeDecodeError` で落ちる。
    `text=False` を明示した呼び出しは bytes のままなので対象外。
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _dotted_name(node.func) in _SUBPROCESS_CALLS):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        if "encoding" in keywords:
            continue
        for name in _TEXT_MODE_KEYWORDS:
            value = keywords.get(name)
            if value is None or (isinstance(value, ast.Constant) and value.value is False):
                continue  # 渡していない／明示的に False＝bytes のまま＝復号は起きない
            lines.append(node.lineno)
            break
    return sorted(lines)


def _relative_to_stringified_lines(tree: ast.AST) -> list[int]:
    """リポ相対パスを `.as_posix()` を挟まず文字列化している箇所の行番号（Windows で `\\` になる）。

    捕まえる中心形は 2 つ：`str(x.relative_to(y))` と f-string の `{x.relative_to(y)}`。どちらも `.as_posix()` を
    挟めば一致しない（`str(x.relative_to(y).as_posix())`／`{...as_posix()}` は外側が別の呼び出しになる）。
    `.parts` など別属性で使う形、Path のまま使う形は文字列化でないので対象外。別名に束ねてから文字列化する形
    （`rel = p.relative_to(r)` … `f"{rel}"`）はデータフロー解析が要るので見逃す（束ねる箇所での `.as_posix()` は規約）。
    """

    def _is_relative_to_call(node: ast.expr | None) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "relative_to"

    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
            if any(_is_relative_to_call(a) for a in node.args):
                lines.append(node.lineno)
        elif isinstance(node, ast.FormattedValue) and _is_relative_to_call(node.value):
            lines.append(node.lineno)
    return sorted(lines)


def run_checks(root: Path) -> list[pm.Problem]:
    """テスト規約・ソース規約の静的検査（種・--test・skip 理由・encoding・相対パスの as_posix 忘れ＝error）。"""
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
                    f"{rel}:{lineno}: pytest.skip/xfail は理由に ISS 参照（ISS-xxxx）が必須（なぜ止め いつ戻すか）",
                )
            )
        for lineno in _subprocess_text_without_encoding_lines(tree):
            problems.append(
                pm.Problem(
                    "error",
                    f'{rel}:{lineno}: subprocess の text=True には encoding="utf-8" が必須'
                    "（省略するとロケール既定＝Windows では cp932 で復号し、UTF-8 の出力で UnicodeDecodeError）",
                )
            )
        for lineno in _relative_to_stringified_lines(tree):
            problems.append(
                pm.Problem(
                    "error",
                    f"{rel}:{lineno}: リポ相対パスの文字列化は `.as_posix()` を使う"
                    "（省略すると Windows で `\\` になり、生成物・指紋キーが OS で食い違う）",
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
