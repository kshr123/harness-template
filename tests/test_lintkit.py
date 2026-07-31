"""lintkit 共有基盤の部品テスト（1 度だけ）。各 lint が個別に持っていた文法・免除・走査を集約した土台を
ここで確かめる＝移行後は各検査から重複テストが消える（機構あたりの意味を上げる）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import pm
from harness.lintkit import Corpus, Rule, ids, run
from harness.lintkit.exempt import validate_exemptions

pytestmark = pytest.mark.unit


# ---- ids（ID・プレースホルダ・語境界の文法） --------------------------------------------------------


def test_placeholder_is_not_a_real_reference() -> None:
    assert ids.is_placeholder("ISS-XXXX")
    assert ids.is_placeholder("ISS-0000")
    assert not ids.is_placeholder("ISS-0042")


def test_temp_unit_refs_collects_work_iss_learning_but_not_placeholders() -> None:
    line = "work/EP-90-x を直し ISS-0042 を閉じ L-026 を踏まえた（例示は ISS-XXXX）"
    assert ids.temp_unit_refs(line) == ["work/EP-90-x", "ISS-0042", "L-026"]
    # プレースホルダ連番だけの行は拾わない。
    assert ids.temp_unit_refs("型録の例：ISS-0000") == []


def test_word_bounded_matches_standalone_name_not_substring_or_path() -> None:
    pat = ids.word_bounded("models.py")
    assert pat.search("保存は `models.py` が担う")  # 独立した語
    assert pat.search("models.py に足す")
    assert not pat.search("src/harness/ds/models.py を参照")  # 別モジュールへのパスの一部は当たらない（直前が /）
    assert not ids.word_bounded("pipeline.py").search("pipeline.pyi は別物")  # 直後が英数なら当たらない


# ---- validate_exemptions（理由必須・fail-closed の免除表検証） ---------------------------------------


def test_validate_exemptions_requires_a_reason() -> None:
    assert validate_exemptions("owner", {"k": "理由"}) == {"k": "理由"}  # 理由あり＝そのまま返す
    with pytest.raises(ValueError, match="理由が空"):
        validate_exemptions("owner", {"docs/a.md": "   "})  # 空・空白だけは不可
    with pytest.raises(ValueError, match="理由が空"):
        validate_exemptions("owner", {("cli.py", "harness.ds"): "  "})  # tuple 鍵も可（boundary_lint 形）


# ---- Corpus（root・相対パス・ast 解析キャッシュ） -----------------------------------------------------


def test_corpus_rel_is_posix(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    f = tmp_path / "docs" / "a.md"
    f.write_text("x", encoding="utf-8")
    assert Corpus(tmp_path).rel(f) == "docs/a.md"  # 常に `/`（Windows でも `\` にしない）


def test_corpus_parse_caches_and_tolerates_syntax_error(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n", encoding="utf-8")
    c = Corpus(tmp_path)
    assert c.parse(good) is not None
    assert c.parse(good) is c.parse(good)  # 2 回目はキャッシュ（同一オブジェクト）
    assert c.parse(bad) is None  # 構文エラーは None（構文検査の代役をしない）


# ---- Rule / run（既存 InvariantCheck の包みと集約） --------------------------------------------------


def test_rule_from_callable_preserves_behavior_and_derives_name_summary(tmp_path: Path) -> None:
    def sample_check(root: Path) -> list[pm.Problem]:
        """一行目が summary になる。"""
        return [pm.Problem("error", f"見た root は {root.name}")]

    rule = Rule.from_callable(sample_check)
    assert rule.name == "sample_check"
    assert rule.summary == "一行目が summary になる。"
    out = rule.scan(Corpus(tmp_path))  # scan は corpus.root を渡して従来どおり呼ぶ
    assert out[0].message.endswith(tmp_path.name)


def test_run_aggregates_rules_over_one_corpus(tmp_path: Path) -> None:
    a = Rule("a", "s", lambda c: [pm.Problem("error", "A")])
    b = Rule("b", "s", lambda c: [pm.Problem("info", "B")])
    problems = run([a, b], tmp_path)
    assert [p.message for p in problems] == ["A", "B"]
