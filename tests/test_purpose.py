"""正本（AGENTS.md・README.md）に目的が書かれ続けていることを守る。

この基盤の最上位の目的は「案件を重ねるほど強くなること」で、他のすべての決まりごとはその手段である。
以前この 2 つの文書は目的を**手段の言葉**（verify がある・作る側と確かめる側を分ける）で書いており、
そこから逆算した設計は機構だけが精緻になって目的から離れた。

目的の文は、消えても他のどの検査も赤くならない（文書は消しても動く）。記憶を持たない将来のセッションが
黙って落とせる場所に、最も落としてはいけない文がある。ここで留める。

対象集合は 2 ファイル固定なので、これは書く人の申告に依存しない（AGENTS「保証の 3 段階」の (b) の条件）。
文言の言い回しまでは縛らない（見出しと、目的の核になる語の実在だけを見る）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_PURPOSE = "案件を重ねるほど強くなる"


def _read(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def test_agents_states_the_purpose_before_the_principles() -> None:
    """AGENTS.md は目的を述べ、しかも原則より前に述べる（原則は目的の手段なので後に来る）。"""
    text = _read("AGENTS.md")
    assert "## 目的" in text
    assert _PURPOSE in text
    assert text.index("## 目的") < text.index("## 原則")


def test_readme_states_the_purpose() -> None:
    """README はテンプレートとして複製され、複製先で最初に読まれる。目的はそこに要る。"""
    assert _PURPOSE in _read("README.md")


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
