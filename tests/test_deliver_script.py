"""画面に埋め込む JS が、構文として成り立っているかの検査。

**この検査が要る理由**：JS は Python の文字列として持っているので、`\\n` のような書き方を素の文字列で
書くと Python 側が本物の改行に変えてしまい、JS の文字列リテラルが途中で切れて構文エラーになる。
そうなると画面の機能（右クリック・セルの編集・追加・削除）が**丸ごと動かなくなる**のに、HTML の
文字列を見る検査は全部通ってしまう（実際にそれで壊れた）。出力を実際に構文解析して止める。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import pytest

from harness.deliver import render
from harness.deliver import wbs as wbs_mod

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 20)


def _page(tmp_path: Path, *, editable: bool) -> str:
    post = frontmatter.Post("")
    meta: dict[str, Any] = {
        "id": "T-0001",
        "kind": "task",
        "status": "todo",
        "title": "設計",
        "start": "2026-08-03",
        "due": "2026-08-07",
    }
    post.metadata.update(meta)
    (tmp_path / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "work" / "T-0001-a.md").write_text(frontmatter.dumps(post), encoding="utf-8")
    built = wbs_mod.build(tmp_path, today=TODAY)
    return render.render_html(built, editable=editable, token="test-token")


def _scripts(html: str) -> list[str]:
    return re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)


def _unterminated_string_lines(source: str) -> list[str]:
    """文字列リテラルの途中で行が終わっている行（本物の改行が入り込んだ跡）。

    JS の構文解析器が無い環境でも、この壊れ方だけは捕まえられるようにしておく。
    """
    bad: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if line.count("'") % 2 == 1 or line.count('"') % 2 == 1:
            bad.append(stripped[:80])
    return bad


@pytest.mark.parametrize("editable", [False, True])
def test_the_embedded_scripts_parse(tmp_path: Path, editable: bool) -> None:
    """埋め込んだ JS が構文として成り立っている（壊れていると画面の機能が丸ごと死ぬ）。"""
    scripts = _scripts(_page(tmp_path, editable=editable))
    assert scripts, "画面に JS が 1 つも埋まっていない"
    node = shutil.which("node")
    for index, source in enumerate(scripts):
        if node is None:  # 構文解析器が無い環境では、壊れ方の型（行の途中で切れた文字列）だけを見る
            assert not _unterminated_string_lines(source), f"script {index} の文字列が行の途中で切れている"
            continue
        path = tmp_path / f"script{index}.js"
        path.write_text(source, encoding="utf-8")
        done = subprocess.run(
            [node, "--check", str(path)], capture_output=True, text=True, encoding="utf-8", check=False
        )
        assert done.returncode == 0, f"script {index} が構文として読めない:\n{done.stderr}"


def test_no_string_literal_is_cut_by_a_real_newline(tmp_path: Path) -> None:
    """文字列リテラルに本物の改行が混ざっていない（この壊れ方が実際に起きた）。"""
    for source in _scripts(_page(tmp_path, editable=True)):
        assert not _unterminated_string_lines(source)
