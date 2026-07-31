"""boundary_lint のテスト：中核（src/harness/*.py）がプロファイルを import しない不変量の検査。

期待値はすべて一時プロジェクトの構成（どの中核モジュールがどの import を持つか）から導く。
最後の 1 本は現リポに対する回帰テスト（中核 → プロファイルの越境が 0 件のまま）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import boundary_lint

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _core(root: Path, name: str, body: str) -> None:
    """一時プロジェクトに中核モジュール src/harness/<name>.py を書く（import はしない＝構文だけ）。"""
    d = root / "src" / "harness"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _profile(root: Path, name: str) -> None:
    """一時プロジェクトにプロファイル src/harness/<name>/profile.py を置く（越境の対象集合は profile.py の走査から
    導かれるので、テストの世界にも参照するプロファイルを実在させる）。"""
    d = root / "src" / "harness" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.py").write_text("PROFILE = object()\n", encoding="utf-8")


def test_core_absolute_import_of_profile_is_error(tmp_path: Path) -> None:
    # 中核が `import harness.ds.models` すると error（絶対 import の越境）。
    _profile(tmp_path, "ds")
    _core(tmp_path, "badcore.py", "import harness.ds.models\n")
    errors = [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]
    assert any("badcore.py" in p.message and "ds" in p.message for p in errors)


def test_core_subpackage_import_of_profile_is_error(tmp_path: Path) -> None:
    # 中核サブパッケージ（profile.py を持たないディレクトリ）配下も対象＝lintkit/ のようなパッケージの越境も
    # 捕まえる（B1：直下だけ見ると死角だった）。相対 import は所属パッケージ harness.sub を起点に解決する。
    _profile(tmp_path, "ds")
    sub = tmp_path / "src" / "harness" / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "corpus.py").write_text("from ..ds import models\n", encoding="utf-8")
    errors = [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]
    assert any("sub/corpus.py" in p.message and "'ds'" in p.message for p in errors)


def test_profile_dir_files_are_not_treated_as_core(tmp_path: Path) -> None:
    # プロファイル配下（profile.py を持つディレクトリ）のファイルは中核でない＝自分の領域を import してよい。
    _profile(tmp_path, "ds")
    (tmp_path / "src" / "harness" / "ds" / "models.py").write_text("import harness.ds.cv\n", encoding="utf-8")
    assert [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"] == []


def test_core_from_import_of_profile_is_error(tmp_path: Path) -> None:
    # `from harness.serve import app` も error。
    _profile(tmp_path, "serve")
    _core(tmp_path, "badcore.py", "from harness.serve import app\n")
    assert any("serve" in p.message for p in boundary_lint.run_checks(tmp_path) if p.level == "error")


def test_core_relative_import_of_profile_is_error(tmp_path: Path) -> None:
    # 相対 import（`from .agent import cli`）も harness.agent に解決して error。
    _profile(tmp_path, "agent")
    _core(tmp_path, "badcore.py", "from .agent import cli\n")
    assert any("agent" in p.message for p in boundary_lint.run_checks(tmp_path) if p.level == "error")


def test_core_lazy_import_inside_function_is_error_and_marked(tmp_path: Path) -> None:
    # 関数内の遅延 import も検出し、メッセージに「遅延 import」と印を付ける（トップレベルだけ見る抜け道を塞ぐ）。
    _profile(tmp_path, "ds")
    _core(tmp_path, "badcore.py", "def go():\n    import harness.ds\n    return harness.ds\n")
    errors = [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]
    assert any("遅延 import" in p.message for p in errors)


def test_core_import_of_nonexistent_profile_name_is_not_flagged(tmp_path: Path) -> None:
    # 越境の対象は実在するプロファイル（profile.py を持つ dir）だけ。存在しない名前の import は越境でない
    # ＝対象集合を手書きの一覧でなく src の走査から導く効果を固定する。
    _core(tmp_path, "core.py", "import harness.notaprofile\n")
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_core_importing_core_is_ok(tmp_path: Path) -> None:
    # 中核が中核（harness.pm 等）を import するのは正常＝error にしない。
    _core(tmp_path, "goodcore.py", "from harness import pm\nimport harness.models\n")
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_core_stdlib_import_is_ok(tmp_path: Path) -> None:
    # 素の stdlib import は当然 error にしない。
    _core(tmp_path, "goodcore.py", "import ast\nfrom pathlib import Path\n")
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_profile_to_profile_import_is_out_of_scope(tmp_path: Path) -> None:
    # 対象は中核（src/harness/*.py）だけ。プロファイル配下（src/harness/ds/…）の越境はこの検査の範囲外。
    sub = tmp_path / "src" / "harness" / "ds"
    sub.mkdir(parents=True)
    (sub / "cli.py").write_text("import harness.agent.cli\n", encoding="utf-8")
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_profile_name_in_string_is_not_flagged(tmp_path: Path) -> None:
    # 文字列・コメントの中の "import harness.ds" は ast では import 文でない＝error にしない（grep との違い）。
    _core(tmp_path, "goodcore.py", 'DOC = "do not import harness.ds here"\n# import harness.serve\n')
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_blank_exempt_reason_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 免除の理由が空＝設定ミス＝即失敗（黙って免除しない・fail closed）。
    monkeypatch.setattr(boundary_lint, "_EXEMPT", {("cli.py", "harness.ds"): "  "})
    _core(tmp_path, "cli.py", "import harness.ds\n")
    with pytest.raises(ValueError, match="理由が空"):
        boundary_lint.run_checks(tmp_path)


def test_exempt_with_reason_suppresses_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 理由つきで免除すれば、その (ファイル, import 先) の越境は error にしない。
    monkeypatch.setattr(boundary_lint, "_EXEMPT", {("cli.py", "harness.ds"): "理由あり"})
    _core(tmp_path, "cli.py", "import harness.ds\n")
    assert not [p for p in boundary_lint.run_checks(tmp_path) if p.level == "error"]


def test_real_repo_core_does_not_import_profiles() -> None:
    # 回帰：現リポの中核（src/harness/*.py）はどのプロファイルも import していない（越境 0 件）。
    errors = [p for p in boundary_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert not errors, "中核がプロファイルを import している:\n" + "\n".join(p.message for p in errors)
