"""fork（複製）と還流の正本が壊れていないことを守る回帰テスト。

対象は本体領域の実ファイル（`docs/template-copy.md`・`.github/workflows/ci.yaml`）で、複製後も残る
（可変領域ではない）。ここが黙って消える／退行すると「案件を重ねるほど強くなる」の前提（配れる・戻せる）が
崩れるので、要点の存在を機械的に固定する。test_purpose.py と同じ作法（正本テキスト・構造の存在確認）。

期待値は「この設計が要求する不変量」から書く（実装の出力の写経ではない）：境界がファイルレベルで排他で
あること・複製シミュレーションの検出器が CI に居ること・還流の判断者と単位が決まっていること。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_COPY = REPO_ROOT / "docs" / "template-copy.md"
CI_YAML = REPO_ROOT / ".github" / "workflows" / "ci.yaml"


def test_template_copy_defines_ownership_boundary() -> None:
    # T-0193：本体領域と案件領域をファイルレベルで排他に定義していること（merge を機械化する前提）。
    text = TEMPLATE_COPY.read_text(encoding="utf-8")
    assert "本体領域" in text and "案件領域" in text
    # 排他の芯：本体領域の代表（src/harness/）と案件領域の代表（work/）が両方名指しされている。
    assert "src/harness/" in text and "work/" in text
    # fork＝git clone であること・upstream で派生元を指すこと（版記録ファイルを作らない設計）。
    assert "fork" in text and "upstream" in text


def test_template_copy_defines_reflux_procedure() -> None:
    # T-0196：還流（案件→本体）の単位・判断者・基準が決まっていること。
    text = TEMPLATE_COPY.read_text(encoding="utf-8")
    assert "還流" in text
    # 単位＝本体領域だけに触る 1 コミット（cherry-pick / PR）。
    assert "cherry-pick" in text
    # 判断者＝テンプレート側の独立レビュー、かつ回数基準を使わない（一般性で判断）。
    assert "独立レビュー" in text
    assert "回数" in text  # 「回数で待たない／回数基準は使わない」を明記していること


def test_ci_has_clone_simulation_detector() -> None:
    # T-0195：複製シミュレーションの検出器が CI に 1 本あること。init-project → uv sync → verify が緑、を回す。
    text = CI_YAML.read_text(encoding="utf-8")
    assert "clone-simulation" in text
    assert "uv run init-project" in text
    assert "uv sync" in text
    assert "uv run verify" in text
