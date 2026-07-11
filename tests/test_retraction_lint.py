"""retraction_lint（撤回した決まりごとの残骸検査）のテスト。

期待値は構成から導く：撤回一覧に名前を 1 つ仕込み、資産の中にその名前を書いた/書かないファイルを置く→
残骸のあるファイルだけが名指しで error になる（変異ガード）。空一覧＝正常（緑）も確かめる。
tests/ は走査対象外なので、この合成データの文字列自身は検査に当たらない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import retraction_lint


def _errors(root: Path) -> list[str]:
    return [p.message for p in retraction_lint.run_checks(root) if p.level == "error"]


@pytest.mark.unit
def test_empty_retracted_is_green() -> None:
    # 出荷状態は撤回一覧が空＝正常（走査もしない）。自リポでも 0 件で通る（生きた回帰）。
    assert retraction_lint.RETRACTED == {}
    assert retraction_lint.run_checks(Path.cwd()) == []


@pytest.mark.unit
def test_residue_in_asset_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 撤回した名前を仕込み、docs 配下にその名前を書いたファイルを置く→名指しの error（掃除を促す）。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"OBSOLETE_THING": "2026-07-11 に廃止（L-999）"})
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("OBSOLETE_THING を使う\n", encoding="utf-8")
    errors = _errors(tmp_path)
    assert len(errors) == 1
    assert "docs/guide.md" in errors[0]
    assert "OBSOLETE_THING" in errors[0]
    assert "2026-07-11" in errors[0]  # 理由（いつ・なぜ）が error 文に載る


@pytest.mark.unit
def test_word_boundary_avoids_substring_false_positive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 部分文字列一致では誤検出する（DEC が DECISION に含まれる等）。語境界一致なので巻き込まない。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"DEC": "決定記録は廃止済み"})
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("DECISION = 1  # 別語であって残骸ではない\n", encoding="utf-8")
    assert _errors(tmp_path) == []  # DECISION は DEC の残骸ではない（語境界で区別・部分文字列一致にしない）


@pytest.mark.unit
def test_word_boundary_matches_standalone_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 単独トークンとして現れれば残骸＝error（上のテストと対で語境界の判定を固める）。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"DEC": "決定記録は廃止済み"})
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("# 旧 DEC 参照が残っている\n", encoding="utf-8")
    assert any("DEC" in m for m in _errors(tmp_path))


@pytest.mark.unit
def test_allowed_places_are_not_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 名前を挙げてよい 2 か所（撤回一覧・撤回記録）は残骸ではない＝検査から除く。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"OBSOLETE_THING": "廃止済み"})
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "learnings.md").write_text("OBSOLETE_THING を撤回した記録\n", encoding="utf-8")
    (tmp_path / "src" / "harness").mkdir(parents=True)
    (tmp_path / "src" / "harness" / "retraction_lint.py").write_text("OBSOLETE_THING\n", encoding="utf-8")
    assert _errors(tmp_path) == []


@pytest.mark.unit
def test_empty_reason_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 理由（いつ・なぜ）が空の撤回は設定ミス＝即失敗（黙って撤回しない・fail closed）。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"X": "   "})
    with pytest.raises(ValueError, match="理由が空"):
        retraction_lint.run_checks(tmp_path)


@pytest.mark.unit
def test_only_scans_persistent_asset_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 一時的な単位（work/・issues/）は複製で消えるので走査対象外（そこに名前が残っても error にしない）。
    monkeypatch.setattr(retraction_lint, "RETRACTED", {"OBSOLETE_THING": "廃止済み"})
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "note.md").write_text("OBSOLETE_THING\n", encoding="utf-8")
    (tmp_path / "issues").mkdir()
    (tmp_path / "issues" / "ISS-0001.md").write_text("OBSOLETE_THING\n", encoding="utf-8")
    assert _errors(tmp_path) == []
