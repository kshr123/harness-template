"""正本（AGENTS.md・README.md）に目的が書かれ続けていることを守る。

この基盤の最上位の目的は「**AI 開発案件を回すのに必要なものを、案件に関わる 3 つの役割（コンサル・
データサイエンティスト・エンジニア）ぶん一式そろえた、複製して使うプロジェクトテンプレート（土台）である**こと」。
他のすべての決まりごとはその手段である。「案件を重ねるほど強くなる」は目的そのものではなく、良い土台である
ことの帰結（目的 4＝案件で得たものが次へ渡り改良が本体へ戻る、の積み重ね）として書く。

以前この 2 つの文書は目的を、手段の言葉（verify がある・作る側と確かめる側を分ける）や、下位の帰結
（案件を重ねるほど強くなる）で書いており、そこから逆算した設計は目的から離れた。ここで正しい最上位を留める。

目的の文は、消えても他のどの検査も赤くならない（文書は消しても動く）。記憶を持たない将来のセッションが
黙って落とせる場所に、最も落としてはいけない文がある。対象集合は 2 ファイル固定なので、書く人の申告に依存しない
（AGENTS「保証の 3 段階」の (b) の条件）。文言の言い回しまでは縛らない（目的の核になる語＝土台・3 役の実在と、
compounding が最上位でなく帰結として後置されている順序だけを見る）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_MARK = "テンプレート"  # 最上位＝複製して使うテンプレート（土台）
_ROLES = ("コンサル", "データサイエンティスト", "エンジニア")  # そろえる 3 役
_COMPOUNDING = "案件を重ねるほど強くなる"  # 下位の帰結（最上位に据えない）


def _read(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def _states_the_top_purpose(text: str) -> bool:
    """最上位の目的（3 役ぶんそろえたテンプレート）の核になる語が在るか。言い回しは縛らない。"""
    return _TEMPLATE_MARK in text and all(role in text for role in _ROLES)


def test_agents_states_the_purpose_before_the_principles() -> None:
    """AGENTS.md は目的を述べ、しかも原則より前に述べる（原則は目的の手段なので後に来る）。"""
    text = _read("AGENTS.md")
    assert "## 目的" in text
    assert text.index("## 目的") < text.index("## 原則")
    assert _states_the_top_purpose(text[text.index("## 目的") : text.index("## 原則")])


def test_readme_states_the_purpose() -> None:
    """README はテンプレートとして複製され、複製先で最初に読まれる。最上位の目的はそこに要る。"""
    assert _states_the_top_purpose(_read("README.md"))


def test_compounding_is_a_consequence_not_the_top_purpose() -> None:
    """「案件を重ねるほど強くなる」は最上位でなく帰結＝目的の核（テンプレート）より後に置く（誤フレーミングの再発防止）。

    以前は AGENTS.md/README がこれを最上位の目的に据えていた。核（テンプレート＋3 役）が先に在り、compounding は
    その後ろで帰結として触れる順序を守る（触れること自体は任意だが、触れるなら先頭に来ない）。
    """
    for name in ("AGENTS.md", "README.md"):
        text = _read(name)
        assert _states_the_top_purpose(text)
        if _COMPOUNDING in text:
            assert text.index(_TEMPLATE_MARK) < text.index(_COMPOUNDING), (
                f"{name}: compounding が目的の核（テンプレート）より前にある＝最上位に据えている"
            )


def test_agents_names_the_three_levels_of_guarantee() -> None:
    """機構を足す前に「どの段階で保証するか」を問う枠組みが、正本に残っていること。"""
    text = _read("AGENTS.md")
    for level in ("構造的に不可能", "機械が検出", "人が気をつける"):
        assert level in text, f"保証の段階 '{level}' が AGENTS.md から消えている"


def test_agents_says_repo_checks_do_not_prevent_tampering() -> None:
    """リポ内の検査は事故防止であって改竄防止ではない、という区別を残す。

    これが消えると、リポ内の検査に改竄防止を期待する設計（無限後退）が復活する。
    """
    text = _read("AGENTS.md")
    assert "事故防止" in text
    assert "改竄防止" in text
