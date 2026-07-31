"""共通の検証コマンドの実体。

一つの入口（uv run check / verify）で、不変条件（invariant＝常に成り立つべき性質）の検査
（`INVARIANT_CHECKS`＝リポジトリ自身の規則が守られているか）と言語ツール
（`checks.toml` の ruff/mypy/pytest＝普遍的な正しさ）を走らせ、合否を返す。CI もローカルもこの同じ入口を使う
＝完了の定義を一致させる。**個々の検査の一覧と要約は `docs/core.md`**（`INVARIANT_CHECKS` と `checks.toml`
から `uv run doc-sync` が生成する。ここに手書きで列挙しない）。
"""

from __future__ import annotations

import itertools
import shlex
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

from harness import (
    boundary_lint,
    code_doc_lint,
    conventions,
    coverage_lint,
    doc_source_lint,
    doc_sync,
    doclint,
    issues,
    pm,
    profile_doc_lint,
    profiles,
    retraction_lint,
    testing,
)
from harness.profiles import InvariantCheck
from harness.testing import markers_in_expr

# レベル：fast（フック相当）→ standard（pre-commit 相当）→ full（CI・done）。
LEVELS = ("fast", "standard", "full")

# 中核の不変条件の検査（どの段階でも走る・順不同で全件集める）。
# プロファイルの検査（例：DS のテーブル定義 data_lint）は .harness/config.toml の profiles から
# 実行時に集める（プロファイル境界。中核はプロファイルを import しない）。
INVARIANT_CHECKS: list[InvariantCheck] = [
    pm.lint,
    pm.spec_lint,
    issues.run_checks,
    doclint.run_checks,
    coverage_lint.run_checks,
    doc_source_lint.run_checks,
    code_doc_lint.run_checks,
    profile_doc_lint.run_checks,
    boundary_lint.run_checks,
    conventions.run_checks,
    retraction_lint.run_checks,
    doc_sync.run_checks,
]


def _glob_to_path_regex(glob: str) -> str:
    """tests/ 直下の glob（例 `test_ds_*.py`）を、mypy --exclude 用のパス正規表現へ変換する。

    mypy は --exclude の正規表現を（相対）パスに re.search で当てる。`*` はディレクトリを跨がない任意列、
    `.` はリテラルのドットにする。末尾を `$` で閉じ、tests/ 配下に限定する。
    """
    body = glob.replace(".", r"\.").replace("*", "[^/]*")
    return rf"tests/{body}$"


def _mypy_exclude_args(root: Path, enabled: list[str] | None = None) -> list[str]:
    """無効なプロファイルのソース（`src/harness/<name>/`）と所有テストを mypy の対象から外す引数。

    非 DS の案件（profiles=[]）では DS 等のソース・テストが optional 依存（polars・fastapi 等）を import するため、
    mypy(strict) が「型スタブが無い」で落ちる。有効化されていない＝そのプロファイルを使わない＝依存も入れない
    前提なので、有効なプロファイルだけを型検査する。全プロファイル有効な当リポでは無効集合が空＝除外なし＝
    従来どおり src と tests 全体を検査する。除外集合の出どころは Profile.test_globs（収集除外と同じ 1 か所）。
    """
    args: list[str] = []
    for profile in profiles.disabled_profiles(root, enabled=enabled):
        args += ["--exclude", rf"src/harness/{profile.name}/"]
        for glob in profile.test_globs:
            args += ["--exclude", _glob_to_path_regex(glob)]
    return args


def _load_commands(root: Path, level: str) -> list[list[str]]:
    """checks.toml から、そのレベルまでに走らせる言語ツールのコマンドを集める。"""

    path = root / "checks.toml"
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    commands: list[list[str]] = []
    for lv in LEVELS[: LEVELS.index(level) + 1]:
        for cmd in data.get(lv, {}).get("commands", []):
            commands.append(cmd)
    return commands


def _registered_markers(root: Path) -> set[str]:
    """pyproject.toml に登録済みのマーカー名の集合（`name: 説明` の name 部分）。ファイル・キーが無ければ空。"""

    path = root / "pyproject.toml"
    if not path.is_file():
        return set()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    return {str(m).split(":")[0].strip() for m in markers}


# 走らせてよいコマンドの allowlist（argv 単位）。**何を走らせてよいか**だけを固定し、段階への割り当て・順序は
# checks.toml が自由に決める。未知の argv は起動を拒否（fail closed）＝「まだ列挙していない次のフラグ」も
# 既定で止まる（denylist のように 1 つずつ潰さない）。
_ALLOWED_RUFF_ARGV: frozenset[tuple[str, ...]] = frozenset({("ruff", "format", "--check", "."), ("ruff", "check", ".")})
_ALLOWED_MYPY_ARGV: frozenset[tuple[str, ...]] = frozenset({("mypy",)})
# pytest コマンドで許すフラグ（引数を取らないもの）。-m は式トークンを 1 つ取るので別扱い。
# 必要になったフラグ（例 -p no:cacheprovider）は、実際に使うものだけを理由つきでここに足す。
_ALLOWED_PYTEST_FLAGS: frozenset[str] = frozenset({"-q"})


def _marker_matcher(present: frozenset[str]) -> Callable[..., bool]:
    """`-m` 式の評価器（`_pytest.mark.expression.Expression`）に渡す照合関数を作る。

    指定したマーカー集合に名前があるかを返す。`foo(bar=1)` のような kwargs 形は使わない（無視する）。
    """

    def matcher(name: str, /, **kwargs: object) -> bool:
        return name in present

    return matcher


def _require_satisfiable_marker_expr(expr: str, cmd: list[str]) -> None:
    """`-m` 式が、PYRAMID の層をちょうど 1 つ持つテストで充足可能かを機械的に確かめる（不能なら ValueError）。

    異なる層（unit/integration/e2e）を and で結ぶ（例 `unit and integration`）と、どのテストも満たせず全
    deselect→exit 5→偽の合格になる。対象の世界は PYRAMID 定数から機械的に列挙する（層 1 つ × その他の
    マーカー〔slow 等〕の真偽の全組み合わせ）＝書く人の申告に依存しない（保証の (b)）。式の意味は pytest 自身の
    評価器（`-m` と同じ）を使う＝手書きの評価器を再発明しない。
    """
    from _pytest.mark.expression import Expression

    try:
        compiled = Expression.compile(expr)
    except Exception as exc:  # 構文エラー等はそのまま起動拒否に倒す（fail closed）
        raise ValueError(f"checks.toml の pytest -m 式が壊れている: {expr!r}（{exc}）: {cmd}") from exc
    free = sorted(markers_in_expr(expr) - set(testing.PYRAMID))  # 層以外の自由なマーカー（slow 等）
    for layer in testing.PYRAMID:
        for bits in itertools.product((False, True), repeat=len(free)):
            present = frozenset({layer, *(name for name, on in zip(free, bits, strict=True) if on)})
            if compiled.evaluate(_marker_matcher(present)):
                return  # 1 つでも選べる世界があれば充足可能
    raise ValueError(
        f"checks.toml の pytest -m 式 {expr!r} は充足不能: PYRAMID の層を 1 つだけ持つどのテストも選べない"
        f"（異なる層 {list(testing.PYRAMID)} を and で結んでいないか）: {cmd}"
    )


def _pytest_markers(cmd: list[str]) -> set[str]:
    """pytest コマンドの引数を allowlist で検査し、-m 式が参照するマーカー集合を返す（未知引数は ValueError）。

    許すのは `-q` と `-m <式>` だけ。未知の引数（-k・--collect-only・--ignore=… 等）は fail closed で拒否する。
    -m が末尾で式が無いときは素の IndexError でなく ValueError にする。式は `_require_satisfiable_marker_expr`
    で充足可能性まで見る。
    """
    markers: set[str] = set()
    args = cmd[1:]
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in _ALLOWED_PYTEST_FLAGS:
            i += 1
        elif tok == "-m":
            if i + 1 >= len(args):
                raise ValueError(f"checks.toml の pytest コマンドの -m に式が無い: {cmd}")
            expr = args[i + 1]
            _require_satisfiable_marker_expr(expr, cmd)
            markers |= markers_in_expr(expr)
            i += 2
        else:
            raise ValueError(
                f"checks.toml の pytest コマンドに許可外の引数 {tok!r}: {cmd}"
                f"（許すのは {sorted(_ALLOWED_PYTEST_FLAGS)} と -m <式> だけ＝未知の引数は fail closed で拒否）"
            )
    return markers


def _verify_checks_config(root: Path) -> None:
    """checks.toml の走らせてよいコマンドを argv allowlist で検査し、外れれば ValueError で起動を拒否する。

    保証すること（allowlist＝fail closed）：走らせてよいのは ruff/mypy の決まった argv と、pytest の
    `-q`・`-m <式>` だけ。未知の引数・未知のコマンド・充足不能な `-m` 式（異なる層の and 等）はすべて
    起動前に ValueError で止まる。「まだ列挙していない次のフラグ」も既定で拒否される（denylist のように
    1 つずつ潰さない）。対象集合はツール自身の定数（LEVELS・testing.PYRAMID・許可 argv 定数）と
    pyproject の登録から機械的に導ける（自己申告の台帳ではない＝保証の (b)）。

    検査対象は checks.toml の**生の argv**（`_load_commands` が読んだもの）だけ。harness 自身が実行時に足す
    引数（`run_check` が mypy に付ける `--exclude …`＝T-0192）は検査しない。ここで実行時の追加分まで禁じると、
    非 DS 案件（profiles=[]）で mypy の除外が付けられず verify が起動しなくなる（allowlist は「人が書いた argv」
    にだけ効く）。

    保証しないこと：これは「事故防止」であって「改竄防止」ではない。この関数を書き換える手は checks.toml を
    書き換える手と同じで、リポ内に不動点は無い（AGENTS「保証の 3 段階」）。後退を止めるのは差分の独立
    レビューと作業ツリー外の required checks。

    番人を pytest の中に置かない：この関数は run_check の冒頭で無条件に呼ぶ。全 pytest テストが deselect
    されても検査は効く（門番が門の内側に住まない）。
    """

    path = root / "checks.toml"
    if not path.is_file():
        # 不存在を寛容にすると _load_commands が空を返し、ruff/mypy/pytest が 1 つも走らないまま verify が
        # 緑になる（黙って全テスト層を失う）。クローンは checks.toml を必ず同梱するので「複製直後でファイルが
        # 無い」状態は起きない＝寛容の根拠が無い。言語検査を持たない状態を望むなら空でなく明示的に書かせ、
        # 下の (1) が「必須の言語検査を欠く」として拒否する一本道に乗せる（fail-closed）。
        raise ValueError(
            f"checks.toml が無い: {path}"
            "（クローンは必ず同梱する。無ければ ruff/mypy/pytest が 1 つも走らず verify が緑になる＝"
            "黙って全テスト層を失う。存在を必須にして fail-closed にする）"
        )
    commands = _load_commands(root, LEVELS[-1])  # full まで＝全レベルのコマンドを累積。

    # 各コマンドを argv allowlist に照合し、外れたら起動を拒否する。pytest の -m 式が参照するマーカーも集める。
    used: set[str] = set()
    for cmd in commands:
        if not cmd:
            raise ValueError("checks.toml に空のコマンドがある（走らせる argv が無い）")
        head = cmd[0]
        if head == "pytest":
            used |= _pytest_markers(cmd)
        elif head == "ruff":
            if tuple(cmd) not in _ALLOWED_RUFF_ARGV:
                allowed = sorted(list(argv) for argv in _ALLOWED_RUFF_ARGV)
                raise ValueError(f"checks.toml が許可外の ruff コマンド: {cmd}（走らせてよいのは {allowed} だけ）")
        elif head == "mypy":
            if tuple(cmd) not in _ALLOWED_MYPY_ARGV:
                raise ValueError(f"checks.toml が許可外の mypy コマンド: {cmd}（走らせてよいのは ['mypy'] だけ）")
        else:
            raise ValueError(
                f"checks.toml が許可外のコマンド: {cmd}"
                "（走らせてよいのは ruff/mypy/pytest の決まった argv だけ＝未知のコマンドは fail closed で拒否）"
            )

    # (1) full までに ruff と mypy が各 1 回以上現れる（言語検査がまるごと抜ける改変を拒否）。
    heads = {cmd[0] for cmd in commands if cmd}
    missing_tools = [tool for tool in ("ruff", "mypy") if tool not in heads]
    if missing_tools:
        raise ValueError(
            f"checks.toml が必須の言語検査を欠く: {missing_tools}（full までに ruff と mypy が各 1 回以上必要）"
        )

    # (2) すべてのマーカーが pyproject に登録済み（綴り違い・改名の typo を拒否＝全 deselect の経路を閉じる）。
    unregistered = sorted(used - _registered_markers(root))
    if unregistered:
        raise ValueError(
            f"checks.toml が未登録のマーカーを参照: {unregistered}"
            "（pyproject.toml の markers に無い＝綴り違い・改名の疑い。放置すると全 deselect で 0 件のまま緑になる）"
        )

    # (3) テストの層（testing.PYRAMID）を -m 式が被覆する（pytest 行や層まるごとの取り外しを拒否）。
    uncovered = sorted(set(testing.PYRAMID) - used)
    if uncovered:
        raise ValueError(
            f"checks.toml の pytest -m 式がテストの層を被覆しない: 未接続の層 {uncovered}"
            f"（各層 {list(testing.PYRAMID)} が段階のどれかに接続されている必要がある）"
        )


def _run_invariant_checks(root: Path) -> bool:
    """不変条件の検査（リポジトリ自身の規則が守られているか）を走らせる。

    参照・壊れた frontmatter・完了↔検証の欠落は失敗。
    STATUS.md は生成物（その都度 `uv run status` で作り直す・コミットしない）なので、
    ここで「生成物とソースの一致」は突き合わせない（古い生成物を理由に検証を落とさない）。
    """

    ok = True
    problems: list[pm.Problem] = []
    all_checks = INVARIANT_CHECKS + [c for p in profiles.load_profiles(root) for c in p.invariant_checks]
    for check in all_checks:
        problems += check(root)
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        print(f"  {mark} {p.message}")
        if p.level == "error":
            ok = False
    if ok:
        # 件数は実測（config で有効にしたプロファイルの検査も数に入る）。内訳の手書き列挙は置かない。
        print(f"  ○ 不変条件の検査 {len(all_checks)} 件すべて通過（内訳は docs/core.md）")
    return ok


def _run_one(root: Path, cmd: list[str]) -> bool:
    """言語ツール 1 コマンドを走らせ、合否を返す。

    - mypy には無効プロファイルの除外引数を実行時に足す（非 DS 案件で optional 依存の型スタブ欠落で落ちないよう。
      checks.toml は `["mypy"]` のまま・除外は profiles から導く＝有効プロファイルの列挙と同じ入口）。
    - pytest の exit 5（選んだ目印に該当するテストが 1 件も無い）は合格扱い（段階×目印の設計上その層が空でも失敗でない。
      付け忘れは conftest の目印ガードが別途止める）。それ以外の非 0 は失敗。
    """
    if cmd[:1] == ["mypy"]:
        cmd = cmd + _mypy_exclude_args(root)
    # shlex.join：空白を含む引数（`-m "unit and not slow"`）を引用する＝表示をそのまま手で再実行できる。
    print(f"  → {shlex.join(cmd)}")
    result = subprocess.run(cmd, cwd=root)
    if result.returncode != 0:
        if result.returncode == 5 and cmd[:1] == ["pytest"]:
            print("    （この目印に該当するテストは無し＝合格）")
            return True
        return False
    return True


def run_check(root: Path, level: str = "full", scope: str = "all") -> int:
    """検証を実行し、終了コードを返す（0=成功・非0=失敗）。

    `scope="all"`（既定）＝レベルに応じて全部走らせる（`verify` は full＝権威ある完了判定）。
    `scope="diff"`＝git 差分に応じて絞る**参考実行**（done の証拠にしない。振り分けの詳細は `harness.scope`）。
    """
    if level not in LEVELS:
        print(f"不明なレベル: {level}（{', '.join(LEVELS)} のいずれか）")
        return 2

    # 起動前の不変条件：checks.toml が壊れていれば、検査を 1 つも走らせずに起動を拒否する（fail-open を塞ぐ）。
    # pytest の中でなくここ（無条件に走る層）に置く＝門番が門の内側に住まない。
    _verify_checks_config(root)

    if scope == "diff":
        return _run_scoped(root)
    if scope != "all":
        print(f"不明なスコープ: {scope}（all | diff のいずれか）")
        return 2

    print(f"[check level={level}]")
    ok = _run_invariant_checks(root)
    for cmd in _load_commands(root, level):
        if not _run_one(root, cmd):
            ok = False
    print("成功（すべて通過）" if ok else "失敗（未通過あり）")
    return 0 if ok else 1


def _run_scoped(root: Path) -> int:
    """git 差分に応じて絞った参考実行。不変条件は毎回全部（安く・横断的なので絞らない）・言語ツールとテストだけ絞る。

    これは advisory＝回さない経路がありうるので done の証拠にしない。分類できない変更・検査インフラ・中核の
    変更は build_plan が全実行（verify と同じ full）に落とす（fail-closed の過近似）。
    """
    from harness import scope as scope_mod

    plan = scope_mod.build_plan(root)
    print("[check scope=diff]（参考実行＝完了判定ではない。done は uv run verify の全成功だけ）")
    print(f"  ・ {plan.reason}")
    ok = _run_invariant_checks(root)
    if plan.full:
        cmds = _load_commands(root, "full")
    else:
        cmds = []
        if plan.run_ruff:
            cmds += [["ruff", "format", "--check", "."], ["ruff", "check", "."]]
        if plan.run_mypy:
            cmds.append(["mypy"])
        if plan.pytest_files:
            cmds.append(["pytest", "-q", "-m", "not slow", *plan.pytest_files])
    for cmd in cmds:
        if not _run_one(root, cmd):
            ok = False
    print("参考実行：問題なし（done の判定は uv run verify）" if ok else "参考実行：未通過あり")
    return 0 if ok else 1
