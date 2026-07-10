"""code_doc_lint のテスト：プロファイルの公開モジュールが正本ドキュメントに載っているか。

期待値はすべて一時プロジェクトの構成（どのプロファイルにどのモジュール・どの docs を置くか）から導く。
最後の 1 本は現リポに対する回帰テスト（全プロファイルの公開モジュールが docs で触れられていること＝
以後の触れ忘れを止める）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import code_doc_lint

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in code_doc_lint.run_checks(root) if p.level == "error"]


def _profile(root: Path, name: str, *modules: str) -> None:
    """プロファイル（profile.py つきディレクトリ）と、その公開モジュールを作る。"""
    _write(root, f"src/harness/{name}/__init__.py", "")
    _write(root, f"src/harness/{name}/profile.py", "PROFILE = object()\n")
    for module in modules:
        _write(root, f"src/harness/{name}/{module}", "")


# --- 検出：ドキュメントで触れられていない公開モジュールは error ---


@pytest.mark.unit
def test_undocumented_module_is_error(tmp_path: Path) -> None:
    _profile(tmp_path, "ds", "pipeline.py", "cv.py")
    _write(tmp_path, "docs/ds.md", "実装の説明。`pipeline.py` は組み立ての中核。\n")
    errors = _errors(tmp_path)
    # pipeline.py は触れられている＝出ない。cv.py は未記載＝出る。
    assert not any("pipeline.py" in m for m in errors)
    assert any("src/harness/ds/cv.py" in m for m in errors)
    # docs に 1 行足すと消える（-code.md 側でも可）。
    _write(tmp_path, "docs/ds-code.md", "`cv.py` は交差検証。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_private_and_dunder_modules_are_ignored(tmp_path: Path) -> None:
    # `__init__.py`・`profile.py`・`_` 始まりは対象外（profile.py は説明不要な結線・私的は非公開）。
    _profile(tmp_path, "serve", "_internal.py")
    _write(tmp_path, "docs/serve.md", "配信の説明（モジュール名は書かない）。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_non_profile_dirs_are_not_scanned(tmp_path: Path) -> None:
    # profile.py の無いディレクトリ（core 直下の共通部品）は対象外。
    _write(tmp_path, "src/harness/lonely.py", "")  # プロファイルでない
    _write(tmp_path, "src/harness/util/__init__.py", "")
    _write(tmp_path, "src/harness/util/helper.py", "")  # profile.py が無い
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_substring_of_sibling_does_not_mask_module(tmp_path: Path) -> None:
    # `lint.py` は `schedule_lint.py` の部分文字列。素朴な部分一致だと schedule_lint.py への言及だけで
    # lint.py が「載っている」ことにされ検査が無効化される。語境界を要求して独立に必要と分かること。
    _profile(tmp_path, "agent", "lint.py", "schedule_lint.py")
    _write(tmp_path, "docs/agent.md", "`schedule_lint.py` は雛形の lint。\n")  # lint.py には触れていない
    errors = _errors(tmp_path)
    assert any("agent/lint.py" in m for m in errors)
    assert not any("schedule_lint.py" in m for m in errors)
    # lint.py を独立に書けば消える。
    _write(tmp_path, "docs/agent-code.md", "`lint.py` は宣言の lint。\n")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_code_doc_only_covers_module(tmp_path: Path) -> None:
    # 正本は <名>.md か <名>-code.md のどちらでもよい（連結して探す）。
    _profile(tmp_path, "agent", "runtime.py")
    _write(tmp_path, "docs/agent.md", "契約の地図（モジュール名は書かない）。\n")
    assert any("runtime.py" in m for m in _errors(tmp_path))
    _write(tmp_path, "docs/agent-code.md", "`runtime.py` は往復ループ。\n")
    assert _errors(tmp_path) == []


# --- 免除リストの規約：理由は空でない文字列が必須 ---


@pytest.mark.unit
def test_every_exempt_reason_is_nonempty() -> None:
    for key, reason in code_doc_lint._EXEMPT.items():
        assert isinstance(reason, str) and reason.strip(), f"_EXEMPT[{key!r}] の理由が空"


@pytest.mark.unit
def test_exempt_suppresses_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(tmp_path, "ds", "legacy.py")
    _write(tmp_path, "docs/ds.md", "モジュール名は書かない。\n")
    assert any("ds/legacy.py" in m for m in _errors(tmp_path))
    monkeypatch.setitem(code_doc_lint._EXEMPT, "ds/legacy.py", "旧経路・撤去予定なので docs から外す（ISS-9999）")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_blank_exempt_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(code_doc_lint._EXEMPT, "ds/foo.py", "  ")
    with pytest.raises(ValueError, match="理由が空"):
        code_doc_lint.run_checks(tmp_path)


# --- 配線：PM_CHECKS に載っている ---


@pytest.mark.unit
def test_code_doc_lint_is_wired_into_pm_checks() -> None:
    from harness import checks

    assert code_doc_lint.run_checks in checks.PM_CHECKS


# --- 回帰テスト：現リポの全プロファイルのモジュールが docs で触れられている ---


@pytest.mark.integration
def test_real_repo_profile_modules_are_documented() -> None:
    errors = [p for p in code_doc_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
