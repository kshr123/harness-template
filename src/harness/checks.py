"""共通の検証コマンドの実体。

一つの入口（uv run check / verify）で、プロジェクト管理の検査（`PM_CHECKS`）と言語ツール
（`checks.toml` の ruff/mypy/pytest）を走らせ、合否を返す。CI もローカルもこの同じ入口を使う
＝完了の定義を一致させる。**個々の検査の一覧と要約は `docs/core.md`**（`PM_CHECKS` と `checks.toml`
から `uv run doc-sync` が生成する。ここに手書きで列挙しない）。
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path

from harness import (
    code_doc_lint,
    conventions,
    coverage_lint,
    doc_source_lint,
    doc_sync,
    doclint,
    issues,
    pm,
    profiles,
    testing,
)
from harness.profiles import PmCheck
from harness.testing import markers_in_expr

# レベル：fast（フック相当）→ standard（pre-commit 相当）→ full（CI・done）。
LEVELS = ("fast", "standard", "full")

# 中核のプロジェクト管理の検査（どの段階でも走る・順不同で全件集める）。
# プロファイルの検査（例：DS のテーブル定義 data_lint）は .harness/config.toml の profiles から
# 実行時に集める（プロファイル境界。中核はプロファイルを import しない）。
PM_CHECKS: list[PmCheck] = [
    pm.lint,
    pm.spec_lint,
    issues.run_checks,
    doclint.run_checks,
    coverage_lint.run_checks,
    doc_source_lint.run_checks,
    code_doc_lint.run_checks,
    conventions.run_checks,
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


def _verify_checks_config(root: Path) -> None:
    """checks.toml の不変条件を検査し、満たさなければ ValueError で起動を拒否する（fail-open を塞ぐ）。

    pytest は「選んだ目印に該当するテストが 0 件」を終了コード 5 で表し、run_check はこれを合格として扱う
    （複製先が層を正当に空にできるようにする意図した寛容さ）。だがマーカーを綴り違え（unit→unitt）ると
    全 deselect で 0 件になり、exit 5 経由で「テストが 1 件も無いのに緑」になる。pytest 行を丸ごと消す・
    ruff/mypy を消す改変も同じく素通りする。これらを、走らせる前の不変条件で閉じる。対象集合はツール自身の
    定数（LEVELS・testing.PYRAMID）と pyproject の登録から機械的に導ける（自己申告の台帳ではない）。

    番人を pytest の中に置かない：この関数は run_check の冒頭で無条件に呼ぶ。全 pytest テストが deselect
    されても検査は効く（門番が門の内側に住まない）。
    """

    path = root / "checks.toml"
    if not path.is_file():
        return  # 複製直後などファイルが無いときは _load_commands と同じく寛容（走らせるものが無いだけ）。
    commands = _load_commands(root, LEVELS[-1])  # full まで＝全レベルのコマンドを累積。

    # (1) full までに ruff と mypy が各 1 回以上現れる（言語検査がまるごと抜ける改変を拒否）。
    first_tokens = {cmd[0] for cmd in commands if cmd}
    missing_tools = [tool for tool in ("ruff", "mypy") if tool not in first_tokens]
    if missing_tools:
        raise ValueError(
            f"checks.toml が必須の言語検査を欠く: {missing_tools}（full までに ruff と mypy が各 1 回以上必要）"
        )

    # pytest -m 式が参照するマーカー名の和集合を集める。
    used: set[str] = set()
    for cmd in commands:
        if cmd[:1] == ["pytest"] and "-m" in cmd:
            used |= markers_in_expr(cmd[cmd.index("-m") + 1])

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


def _pm_checks(root: Path) -> bool:
    """プロジェクト管理の決まりごとを検査する。参照エラー・壊れた frontmatter・完了↔検証の欠落は失敗。

    STATUS.md は生成物（その都度 `uv run status` で作り直す・コミットしない）なので、
    ここで「生成物とソースの一致」は突き合わせない（古い生成物を理由に検証を落とさない）。
    """

    ok = True
    problems: list[pm.Problem] = []
    all_checks = PM_CHECKS + [c for p in profiles.load_profiles(root) for c in p.pm_checks]
    for check in all_checks:
        problems += check(root)
    for p in problems:
        mark = "✗" if p.level == "error" else "・"
        print(f"  {mark} {p.message}")
        if p.level == "error":
            ok = False
    if ok:
        # 件数は実測（config で有効にしたプロファイルの検査も数に入る）。内訳の手書き列挙は置かない。
        print(f"  ○ プロジェクト管理の検査 {len(all_checks)} 件すべて通過（内訳は docs/core.md）")
    return ok


def run_check(root: Path, level: str = "full") -> int:
    """検証を実行し、終了コードを返す（0=成功・非0=失敗）。"""

    if level not in LEVELS:
        print(f"不明なレベル: {level}（{', '.join(LEVELS)} のいずれか）")
        return 2

    # 起動前の不変条件：checks.toml が壊れていれば、検査を 1 つも走らせずに起動を拒否する（fail-open を塞ぐ）。
    # pytest の中でなくここ（無条件に走る層）に置く＝門番が門の内側に住まない。
    _verify_checks_config(root)

    print(f"[check level={level}]")
    ok = _pm_checks(root)

    for cmd in _load_commands(root, level):
        # 無効なプロファイルのソース・テストを mypy の対象から外す（非 DS 案件では optional 依存が無い＝
        # そのままだと strict が「型スタブが無い」で落ちる）。checks.toml は `["mypy"]` のまま・除外は
        # profiles から実行時に導く（有効なプロファイルの列挙と同じ入口）。当リポは全有効＝除外なし。
        if cmd[:1] == ["mypy"]:
            cmd = cmd + _mypy_exclude_args(root)
        # shlex.join：空白を含む引数（`-m "unit and not slow"`）を引用する＝表示をそのまま手で再実行できる。
        print(f"  → {shlex.join(cmd)}")
        result = subprocess.run(cmd, cwd=root)
        if result.returncode != 0:
            # pytest は「選んだ目印に該当するテストが 1 件も無い」を終了コード 5 で表す。
            # 段階×目印の設計上、その層のテストがまだ無いのは失敗ではない（付け忘れは conftest の
            # 目印ガードが別途止める）。5 だけは成功として扱い、それ以外の非 0 は失敗にする。
            if result.returncode == 5 and cmd[:1] == ["pytest"]:
                print("    （この目印に該当するテストは無し＝合格）")
                continue
            ok = False

    print("成功（すべて通過）" if ok else "失敗（未通過あり）")
    return 0 if ok else 1
