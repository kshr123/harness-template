"""profile_doc_lint のテスト：各プロファイルの正本 docs/<名>.md が入口（docs/README.md）から辿れるか。

期待値は一時プロジェクトの構成（どのプロファイルを置き・索引に何を載せたか）から導く。
最後の 1 本は現リポの回帰テスト（同梱プロファイルの正本がすべて索引から辿れる）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import checks, profile_doc_lint

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _profile(root: Path, name: str) -> None:
    d = root / "src" / "harness" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.py").write_text("PROFILE = object()\n", encoding="utf-8")


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in profile_doc_lint.run_checks(root) if p.level == "error"]


def test_profile_with_doc_linked_from_index_is_ok(tmp_path: Path) -> None:
    _profile(tmp_path, "foo")
    _write(tmp_path, "docs/foo.md", "# foo\n")
    _write(tmp_path, "docs/README.md", "索引: [foo.md](foo.md)\n")
    assert _errors(tmp_path) == []


def test_missing_canonical_doc_is_error(tmp_path: Path) -> None:
    _profile(tmp_path, "foo")
    _write(tmp_path, "docs/README.md", "索引（foo.md への行はまだ無い）\n")
    assert any("docs/foo.md が無い" in m for m in _errors(tmp_path))


def test_doc_exists_but_not_linked_in_index_is_error(tmp_path: Path) -> None:
    # stats がまさにこの形だった：正本 docs/<名>.md は在るのに、索引に載せ忘れて入口から到達不能。
    _profile(tmp_path, "foo")
    _write(tmp_path, "docs/foo.md", "# foo\n")
    _write(tmp_path, "docs/README.md", "索引（foo への行を書き忘れた）\n")
    assert any("索引が docs/foo.md を載せていない" in m for m in _errors(tmp_path))


def test_link_match_is_by_target_not_bare_substring(tmp_path: Path) -> None:
    # 素の名前の部分一致だと `ds` が `odds.md` に当たってしまう。リンク先 `(名.md)` で照合するので誤検知しない
    # ＝odds.md しか無い索引では ds は「未リンク」として正しく error。
    _profile(tmp_path, "ds")
    _write(tmp_path, "docs/ds.md", "# ds\n")
    _write(tmp_path, "docs/README.md", "索引: [odds.md](odds.md)\n")
    assert any("索引が docs/ds.md を載せていない" in m for m in _errors(tmp_path))


def test_link_match_accepts_path_prefix_and_anchor(tmp_path: Path) -> None:
    # パス前置き（docs/foo.md）・アンカー（foo.md#節）でリンクしても「辿れる」と認める（false-positive を出さない）。
    _profile(tmp_path, "foo")
    _write(tmp_path, "docs/foo.md", "# foo\n")
    _write(tmp_path, "docs/README.md", "パス: [foo](docs/foo.md)・アンカー: [節](foo.md#使い方)\n")
    assert _errors(tmp_path) == []


def test_wired_into_invariant_checks() -> None:
    assert profile_doc_lint.run_checks in checks.INVARIANT_CHECKS


@pytest.mark.integration
def test_real_repo_profiles_are_reachable_from_index() -> None:
    errors = [p for p in profile_doc_lint.run_checks(REPO_ROOT) if p.level == "error"]
    assert errors == [], [p.message for p in errors]
