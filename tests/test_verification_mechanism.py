"""検証の仕組み（段階×目印）の部品テスト。

目印ガードの純粋関数を、構成から導ける入力で確かめる（実装をなぞらない）。
フック本体（conftest の pytest_collection_modifyitems）は、この関数が正しければ薄い包みなので、
「全テストが目印を持つ」ことはスイート全体が collect を通ること自体が裏付ける（無印を置けば collect で失敗する）。
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

from harness import checks, profiles
from harness.testing import PYRAMID, markers_in_expr, unmarked

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]  # harness-template リポの根


def test_unmarked_detects_only_pyramid_missing() -> None:
    rows = [
        ("tests/a.py::t1", {"unit"}),
        ("tests/b.py::t2", set()),  # 目印なし＝迷子
        ("tests/c.py::t3", {"integration", "slow"}),
        ("tests/d.py::t4", {"slow"}),  # slow だけ＝ピラミッドの目印が無い＝迷子
    ]
    # 期待は入力の構成から直に導ける：ピラミッド(unit/integration/e2e)を持たない t2 と t4 だけ。
    assert unmarked(rows) == ["tests/b.py::t2", "tests/d.py::t4"]


def test_all_marked_returns_empty() -> None:
    rows = [("x::a", {"unit"}), ("x::b", {"e2e"})]
    assert unmarked(rows) == []


def test_load_commands_scopes_pytest_by_level(tmp_path: Path) -> None:
    # 段階（level）ごとに pytest の目印選択が変わり、full は累積で3層すべてを含むこと。
    (tmp_path / "checks.toml").write_text(
        "[fast]\ncommands = [['ruff','check','.'],['pytest','-q','-m','unit and not slow']]\n"
        "[standard]\ncommands = [['mypy'],['pytest','-q','-m','integration and not slow']]\n"
        "[full]\ncommands = [['pytest','-q','-m','e2e and not slow']]\n",
        encoding="utf-8",
    )
    fast = checks._load_commands(tmp_path, "fast")
    full = checks._load_commands(tmp_path, "full")
    assert ["pytest", "-q", "-m", "unit and not slow"] in fast
    assert ["pytest", "-q", "-m", "integration and not slow"] not in fast  # fast は unit だけ
    pytest_cmds = [c for c in full if c[:1] == ["pytest"]]
    assert len(pytest_cmds) == 3  # full は unit/integration/e2e の3つを累積で持つ


def test_markers_in_expr_extracts_names() -> None:
    # 論理演算子を除いたマーカー名だけを取り出す（入力の構成から導ける）。
    assert markers_in_expr("e2e and not slow") == {"e2e", "slow"}
    assert markers_in_expr("unit") == {"unit"}


def test_checks_toml_uses_only_registered_markers() -> None:
    # 実 checks.toml の -m 式が参照するマーカーが、pyproject に登録済みであること。
    # 綴り違い・改名で「全 deselect→テスト0件なのに合格（門番の空回り）」になるのを塞ぐ。
    checks_toml = tomllib.loads((_ROOT / "checks.toml").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    registered = {m.split(":")[0].strip() for m in pyproject["tool"]["pytest"]["ini_options"]["markers"]}
    used: set[str] = set()
    for level in checks_toml.values():
        for cmd in level.get("commands", []):
            if cmd[:1] == ["pytest"] and "-m" in cmd:
                used |= markers_in_expr(cmd[cmd.index("-m") + 1])
    assert used <= registered, f"checks.toml が未登録マーカーを使用: {sorted(used - registered)}"
    # 層の 3 目印（unit/integration/e2e）＋除外の 2 目印（slow・browser）が接続されている
    # （どれかが設定から抜け落ちていない）。browser は standard の integration から除外＝Chrome を毎回起動しない。
    assert used == {"unit", "integration", "e2e", "slow", "browser"}


def test_retracted_checks_are_not_re_registered() -> None:
    # EP-53 の撤回の後戻り防止（loops.py の tombstone と同じ作法）：
    # retraction_lint（RETRACTED={} で常に空＝no-op）と pm.spec_lint（SPEC 見出しの有無だけの儀式）は
    # INVARIANT_CHECKS から外した。誤って戻すとここで落ちる。
    # 名前は doc_sync._name（Rule も callable も同じ規則で名付ける＝Rule 化された検査も見落とさない）で集める。
    from harness import doc_sync

    registered = " ".join(doc_sync._name(c) for c in checks.INVARIANT_CHECKS)
    assert "spec_lint" not in registered, "pm.spec_lint は EP-53 で撤回済み（見出し有無だけの儀式）"
    assert "retraction_lint" not in registered, "retraction_lint は EP-53 で撤回済み（常に空の no-op）"
    assert importlib.util.find_spec("harness.retraction_lint") is None, "retraction_lint モジュールは削除済み"


def test_merge_pytest_collapses_layers_into_one_union() -> None:
    # full の 3 つの pytest を 1 本の論理和にまとめる＝走るテスト集合は 3 回実行に完全一致（門番が黙って減らない）。
    cmds = [
        ["ruff", "check", "."],
        ["pytest", "-q", "-m", "unit and not slow"],
        ["mypy"],
        ["pytest", "-q", "-m", "integration and not slow and not browser"],
        ["pytest", "-q", "-m", "e2e and not slow"],
    ]
    merged = checks._merge_pytest(cmds)
    pytest_cmds = [c for c in merged if c[:1] == ["pytest"]]
    assert len(pytest_cmds) == 1  # 3 つ → 1 つ
    # 式は各層の論理和＝和集合（pytest の -m は式の or がテストの和集合）。
    assert pytest_cmds[0] == [
        "pytest",
        "-q",
        "-m",
        "(unit and not slow) or (integration and not slow and not browser) or (e2e and not slow)",
    ]
    assert ["ruff", "check", "."] in merged and ["mypy"] in merged  # 他コマンドは残る


def test_merge_pytest_leaves_single_or_nonstandard_pytest_untouched() -> None:
    # pytest が 1 本ならそのまま。-k・パス付きなど同形でない pytest はまとめない（式の合成が自明でない＝安全側）。
    one = [["pytest", "-q", "-m", "unit and not slow"]]
    assert checks._merge_pytest(one) == one
    nonstd = [["pytest", "-q", "-m", "unit", "-k", "foo"], ["pytest", "-q", "-m", "e2e and not slow"]]
    # 同形（len==4）は 1 本だけなので合流は起きず、そのまま。
    assert checks._merge_pytest(nonstd) == nonstd


# ---- checks.toml の不変条件（起動時 precondition。T-0198 / EP-32） --------------------------------
#
# 番人が門の内側に住まないことの担保：ここで確かめる `_verify_checks_config` は pytest のテストではなく
# `run_check` の冒頭で無条件に呼ばれる関数（マーカーで deselect され得ない）。下の各テストは、その関数を
# 直接呼ぶ（マーカー選択に依存しない層）＋ `run_check` が pytest サブプロセスに到達する前に落ちること
# （＝マーカー選択の上流で効くこと）を確かめる。tmp_path 上に checks.toml／pyproject.toml を組み立てるので、
# 実リポジトリの値はハードコードしない（期待値は組み立てた入力から導ける）。


def _write_repo(tmp_path: Path, *, fast: str, standard: str, full: str) -> Path:
    """tmp_path に checks.toml と、テストの層＋slow を登録した pyproject.toml を置く。

    登録マーカーは testing.PYRAMID（unit/integration/e2e）＋slow から機械的に作る（実 pyproject を仮定しない）。
    """
    (tmp_path / "checks.toml").write_text(
        f"[fast]\ncommands = [{fast}]\n[standard]\ncommands = [{standard}]\n[full]\ncommands = [{full}]\n",
        encoding="utf-8",
    )
    markers = ", ".join(f'"{name}: 層 {name}"' for name in (*PYRAMID, "slow"))
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.pytest.ini_options]\nmarkers = [{markers}]\n",
        encoding="utf-8",
    )
    return tmp_path


# 実リポジトリと同じ形の、正しい段階割り当て（各層が -m 式に一度ずつ現れ、ruff/mypy も揃う）。
_GOOD_FAST = "['ruff','format','--check','.'],['ruff','check','.'],['pytest','-q','-m','unit and not slow']"
_GOOD_STANDARD = "['mypy'],['pytest','-q','-m','integration and not slow']"
_GOOD_FULL = "['pytest','-q','-m','e2e and not slow']"


def test_checks_config_accepts_valid_config(tmp_path: Path) -> None:
    # 実物と同じ形（ruff/mypy 揃い・3 層すべて被覆）は素通りする＝正しい設定を拒まない。
    root = _write_repo(tmp_path, fast=_GOOD_FAST, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    checks._verify_checks_config(root)  # 例外を投げなければ合格


def test_checks_config_rejects_marker_typo(tmp_path: Path) -> None:
    # unit → unitt の綴り違い。unitt は pyproject の登録に無い（全 deselect で 0 件のまま緑になる経路）。
    typo_fast = _GOOD_FAST.replace("unit and not slow", "unitt and not slow")
    root = _write_repo(tmp_path, fast=typo_fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="unitt"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_pytest_layer(tmp_path: Path) -> None:
    # pytest の行を丸ごと消す（ruff/mypy は残す）→ どの層も -m 式に現れず、層の被覆に失敗する。
    root = _write_repo(
        tmp_path,
        fast="['ruff','format','--check','.'],['ruff','check','.']",
        standard="['mypy']",
        full="",
    )
    with pytest.raises(ValueError):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_ruff(tmp_path: Path) -> None:
    # ruff を消す（mypy・pytest は残す）→ 必須の言語検査を欠くので拒否。
    root = _write_repo(
        tmp_path,
        fast="['pytest','-q','-m','unit and not slow']",
        standard=_GOOD_STANDARD,
        full=_GOOD_FULL,
    )
    with pytest.raises(ValueError, match="ruff"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_mypy(tmp_path: Path) -> None:
    # mypy を消す（ruff・pytest は残す）→ 必須の言語検査を欠くので拒否。
    root = _write_repo(
        tmp_path,
        fast=_GOOD_FAST,
        standard="['pytest','-q','-m','integration and not slow']",
        full=_GOOD_FULL,
    )
    with pytest.raises(ValueError, match="mypy"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_missing_file(tmp_path: Path) -> None:
    # checks.toml が無い＝寛容にすると言語検査ゼロで緑になる（黙って全テスト層を失う）。存在を必須にして拒否する。
    # 期待値（拒否）は入力の構成から導ける：ファイルを一切書かない tmp_path なので不存在が確定する。
    with pytest.raises(ValueError, match="checks.toml が無い"):
        checks._verify_checks_config(tmp_path)


def test_run_check_rejects_missing_config_before_pytest(tmp_path: Path) -> None:
    # 番人が門の内側に住まない証拠（不存在版）：checks.toml が無い root の run_check は、pytest に到達する
    # 前（無条件の層）で ValueError を投げる＝「ファイルを消せば緑」の経路を上流で断つ。
    with pytest.raises(ValueError, match="checks.toml が無い"):
        checks.run_check(tmp_path, "full")


def test_run_check_rejects_broken_config_before_pytest(tmp_path: Path) -> None:
    # 番人が門の内側に住まない証拠：壊れた checks.toml を与えた run_check は、pytest サブプロセスに
    # 到達する前（＝マーカー選択の上流・無条件の層）で ValueError を投げる。pytest が 1 件も走らなくても
    # 起動が拒否されることを、run_check を直接呼んで確かめる。
    typo_fast = _GOOD_FAST.replace("unit and not slow", "unitt and not slow")
    root = _write_repo(tmp_path, fast=typo_fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError):
        checks.run_check(root, "full")


# ---- argv allowlist（T-0209 / EP-32）：名前の存在でなく「走らせてよい argv」を固定し、未知は fail closed ----
#
# 独立レビューが実測した「テスト 0 件のまま緑」経路を、tmp_path 上の checks.toml で 1 つずつ拒否されることを
# 確かめる。期待値（拒否）は入力の構成から導ける（allowlist の外＝拒否）。denylist で個別に潰したのではなく、
# 許した argv 以外を止めているので「次のフラグ」も同じ理由で止まる。


def test_checks_config_rejects_collapsed_layers(tmp_path: Path) -> None:
    # 3 層を 1 つの -m に and で集約＝積は空集合（どのテストも選べない）→ 充足不能で拒否（exit 5 の偽合格を断つ）。
    fast = _GOOD_FAST.replace("unit and not slow", "unit and integration and e2e")
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="充足不能"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_extra_k_arg(tmp_path: Path) -> None:
    # 正しい -m に -k zzz_never_match を追加＝全 deselect→exit 5→偽の合格の経路。-k は許可外の引数で拒否。
    fast = _GOOD_FAST.replace(
        "'pytest','-q','-m','unit and not slow'",
        "'pytest','-q','-m','unit and not slow','-k','zzz_never_match'",
    )
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外の引数"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_collect_only(tmp_path: Path) -> None:
    # --collect-only を追加＝1 件も実行せず exit 0。許可外の引数で拒否。
    fast = _GOOD_FAST.replace(
        "'pytest','-q','-m','unit and not slow'",
        "'pytest','-q','-m','unit and not slow','--collect-only'",
    )
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外の引数"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_ignore_arg(tmp_path: Path) -> None:
    # --ignore=tests を追加＝収集対象を消して exit 0。許可外の引数で拒否。
    fast = _GOOD_FAST.replace(
        "'pytest','-q','-m','unit and not slow'",
        "'pytest','-q','-m','unit and not slow','--ignore=tests'",
    )
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外の引数"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_hollow_ruff_version(tmp_path: Path) -> None:
    # ruff を --version に骨抜き＝先頭トークンだけ見るなら通っていた。argv allowlist の外なので拒否。
    fast = _GOOD_FAST.replace("'ruff','check','.'", "'ruff','--version'")
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外の ruff"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_hollow_mypy_version(tmp_path: Path) -> None:
    # mypy を --version に骨抜き。argv allowlist の外なので拒否。
    standard = _GOOD_STANDARD.replace("'mypy'", "'mypy','--version'")
    root = _write_repo(tmp_path, fast=_GOOD_FAST, standard=standard, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外の mypy"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_unknown_top_command(tmp_path: Path) -> None:
    # ruff/mypy/pytest 以外の未知コマンドは fail closed で拒否（allowlist の外）。
    fast = _GOOD_FAST + ",['echo','hi']"
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="許可外のコマンド"):
        checks._verify_checks_config(root)


def test_checks_config_rejects_dangling_m(tmp_path: Path) -> None:
    # -m が末尾で式が無い＝素の IndexError でなく ValueError で拒否する。
    fast = _GOOD_FAST.replace("'pytest','-q','-m','unit and not slow'", "'pytest','-q','-m'")
    root = _write_repo(tmp_path, fast=fast, standard=_GOOD_STANDARD, full=_GOOD_FULL)
    with pytest.raises(ValueError, match="-m に式が無い"):
        checks._verify_checks_config(root)


def test_checks_config_accepts_stage_reassignment(tmp_path: Path) -> None:
    # 複製先が段階への割り当てを変える自由：3 層すべてを full に寄せても、argv が allowlist 内なら通る
    # （固定するのは「何を走らせてよいか」だけ・段階の割り当てではない）。`層 and not slow` は正当。
    root = _write_repo(
        tmp_path,
        fast="['ruff','format','--check','.'],['ruff','check','.']",
        standard="['mypy']",
        full="['pytest','-q','-m','unit and not slow'],['pytest','-q','-m','integration and not slow'],"
        "['pytest','-q','-m','e2e and not slow']",
    )
    checks._verify_checks_config(root)  # 例外を投げなければ合格（正当な使い方を壊さない）


# ---- mypy の対象をプロファイルに連動させる（非 DS 案件で profile ソース・テストを型検査から外す＝T-0192） ----
#
# 期待値は Profile.test_globs（プロファイルの持ち物の宣言）と無効集合から導出する（実 config を仮定しない）。

_MECH_ROOT = Path(__file__).resolve().parents[1]


def test_glob_to_path_regex_matches_tests_dir_files() -> None:
    # glob → 正規表現：`*` はディレクトリを跨がず、`.` はリテラル、末尾は $。tests/ 配下だけに当たる。
    import re

    pat = checks._glob_to_path_regex("test_ds_*.py")
    assert re.search(pat, "tests/test_ds_pipeline.py")
    assert not re.search(pat, "tests/test_dsx.py")  # test_ds_ の下線が要る
    assert not re.search(pat, "src/harness/ds/models.py")  # tests/ 配下限定


def test_mypy_excludes_empty_when_all_profiles_enabled() -> None:
    # 全プロファイル有効（当リポの verify と同じ状態）＝無効集合が空＝除外なし＝src と tests 全体を型検査。
    shipped = [f"harness.{p.name}" for p in profiles.discover_profiles(_MECH_ROOT).values()]
    assert checks._mypy_exclude_args(_MECH_ROOT, enabled=shipped) == []


def test_mypy_excludes_disabled_profile_source_and_tests() -> None:
    # profiles=[] なら、無効な各プロファイルの src/harness/<name>/ と所有テスト glob が --exclude に並ぶ。
    args = checks._mypy_exclude_args(_MECH_ROOT, enabled=[])
    # --exclude と値が交互（対で並ぶ）。
    assert args[0::2] == ["--exclude"] * (len(args) // 2)
    patterns = args[1::2]
    for name in ("ds", "serve", "agent", "ops"):
        assert rf"src/harness/{name}/" in patterns  # 無効プロファイルのソースを型検査から外す
    # ds を有効にすると、その分だけ除外が減る（ds ソースは patterns から消える）。
    with_ds = checks._mypy_exclude_args(_MECH_ROOT, enabled=["harness.ds"])[1::2]
    assert r"src/harness/ds/" not in with_ds
    assert r"src/harness/serve/" in with_ds
