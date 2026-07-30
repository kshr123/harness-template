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


def test_lane_click_computes_the_day_in_utc(tmp_path: Path) -> None:
    """レーンの空きクリックで日付を出す `dayAt` は UTC でそろえる（JST など UTC+ で 1 日ずれない）。

    `new Date('YYYY-MM-DDT00:00:00')`（オフセット無し＝ローカル）＋`toISOString()`（UTC）だと、UTC+ の
    時間帯では日付が 1 日戻り、クリックした日の前日が正本に書かれる（実際に起きた）。パースも加算も出力も
    UTC で統一していることを構造で固定する（node の DOM 無しで振る舞いテストが難しいので、退行の形を止める）。
    """
    html = _page(tmp_path, editable=True)
    edit = next(s for s in _scripts(html) if "function dayAt(" in s)
    body = edit.split("function dayAt(", 1)[1].split("}", 1)[0]
    # コメントを除いた実コードだけを見る（説明文には退行形の字面が出てよい）。
    code = "\n".join(ln.split("//", 1)[0] for ln in body.splitlines())
    assert "new Date(first+'T00:00:00Z')" in code and "setUTCDate" in code  # UTC でパース・加算
    assert "new Date(first+'T00:00:00')" not in code and "d.setDate(" not in code  # ローカル解釈の退行形を禁じる


def test_the_event_form_never_shows_the_rrule_expression(tmp_path: Path) -> None:
    """出来事フォームは画面の操作（種類・曜日・初回/最終）だけで完結し、RRULE の文字列（専門用語）を出さない。

    RRULE は誰でも読めないので、画面に見せない＝裏で組み立てて送るだけ。人が使う語（毎週・隔週・毎月第N・
    単発）は残す。「規則（…直接書いてもよい）」のような数式入力欄を出していないことを固定する。
    """
    html = _page(tmp_path, editable=True)
    assert "毎週" in html and "隔週" in html and "毎月第N" in html and "単発" in html  # 人が使う語は残す
    assert "規則（" not in html  # 数式の入力欄ラベル（規則（…））を出さない
    assert "直接編集" not in html and "直接書いても" not in html  # 「直接書ける」導線も消す
    # 数式を見せる行は row('規則…', rule) で作っていた＝その呼び出しが無いこと（rule は控えの変数に降格）。
    assert "row('規則" not in html and 'row("規則' not in html


def test_the_fold_controls_target_only_toggle_buttons(tmp_path: Path) -> None:
    """折りたたみ／展開・個別クリックが対象にするのは親行の button.tw だけ（末端の空 span.tw に三角を書かない・E）。

    素の `.tw` を対象にすると、子を持たない末端行の空 `<span class="tw">` にも `▸`/`▾` が書き込まれてしまう。
    実際の runtime 挙動は test_deliver_browser の実測が確かめる。ここは選択子の逆戻りを常時（Chrome 無しでも）止める。
    """
    html = _page(tmp_path, editable=False)
    assert '<span class="tw"></span>' in html  # 末端は三角を持たない空の span
    assert "querySelectorAll('button.tw')" in html  # 一括トグルの対象は実ボタンに限る
    assert "closest('button.tw')" in html  # 個別クリックも実ボタンに限る
    assert "querySelectorAll('.tw')" not in html  # 素の .tw を巻き込まない
    assert "closest('.tw')" not in html
