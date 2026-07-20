"""中核の正本ドキュメント（`docs/core.md`）の自動生成と鮮度検査（doc_sync）。

`uv run verify` が何を回すかの内訳は、これまで 6 か所に手書きで複製されていて、全部が違い、全部が古かった
（検査を足しても誰も追随できない＝複製がある限り必ず腐る）。要約の出所を 1 つに定めてしまえば、複製は
機械が維持する派生物になる。ここでは次の 2 つを唯一の出所として Markdown 表を生成する：

- `checks.INVARIANT_CHECKS` … 各検査関数の名前（`<モジュール>.<関数>`）と **docstring 1 行目**（＝要約）。
- `checks.toml` … 段階（fast/standard/full）ごとの言語ツールのコマンド。

生成した表は `docs/core.md` のマーカーで囲んだ節に書き込み、**生成物をコミットする**（`docs/core.md` は
他の正本から参照される読み物なので、`STATUS.md` のような「見たいときに作り直す」扱いにはできない）。
コミットする以上は内容が最新かを検査する必要があるので、`run_checks` が生成し直した内容と突き合わせ、
食い違えば verify を失敗させる（生成物をコミットし CI で `git diff --exit-code` する運用と同じやり方）。
`doc_sync.run_checks` 自身も `INVARIANT_CHECKS` の一員なので表に載る（表の完全性の定義そのもの）。

設計上の決め事:
- **`.harness/config.toml` を読まない**。プロファイル（ds・serve・agent・ops）の検査は実行時に config から
  加わるので、生成表は中核の `INVARIANT_CHECKS` だけを対象にする。これで生成結果はどの複製先でも同一になり、
  非 DS の案件（profiles = []）でも `docs/core.md` は変わらない。config に依存した実数を出すのは
  `checks.py` の実行時の表示だけ。
- **docstring 1 行目が無い・空の検査関数は ValueError**（黙って空欄の行を生成しない＝fail closed。
  `coverage_lint._validated_exempt`・`code_doc_lint._validated_exempt` と同じ作法）。
- **`docs/core.md` が無ければ指摘しない**。削除の検出は doclint に委ねる（`AGENTS.md` が `docs/core.md` を
  参照しているので、消せば死にリンクとして落ちる）。
- **改行は LF 固定**（書き出しは `newline="\\n"`。読み取りは universal newlines なので、Windows の作業ツリーが
  CRLF でも比較は成立する）。

検出できない腐り方が 1 つある：**正しい表をマーカーの外に複製する**と、この検査は素通りする（マーカーを
含めて複製すれば「1 組でない」で落ちる）。恒久ドキュメントに検査の項目を手書きしないこと自体は
レビュー観点として残る。

core の検査（プロファイル非依存）。stdlib のみに依存。循環 import を避けるため `harness.checks` は
関数の中で import する（`checks` は `INVARIANT_CHECKS` を組み立てるためにこのモジュールを先に import する）。
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Callable
from pathlib import Path

from harness import pm

# 生成先と、生成する節を囲むマーカー（この 2 行の間だけが自動生成の対象範囲）。
DOC_REL = "docs/core.md"
MARKER_BEGIN = "<!-- doc-sync:begin ここから uv run doc-sync が生成する。手で編集しない。 -->"
MARKER_END = "<!-- doc-sync:end -->"

# 生成する 2 つの表の見出し（`docs/core.md` の散文からも参照される）。
HEADING_CHECKS = "### 不変条件の検査（`INVARIANT_CHECKS`）"
HEADING_COMMANDS = "### 言語ツール（`checks.toml`）"


def _name(check: Callable[[Path], list[pm.Problem]]) -> str:
    """検査関数の表示名。一律 `<モジュール>.<関数>`（`pm.lint`・`doclint.run_checks`）。特例は作らない。"""
    return f"{check.__module__.removeprefix('harness.')}.{check.__name__}"


def _summary(check: Callable[[Path], list[pm.Problem]]) -> str:
    """検査関数の要約＝docstring の 1 行目。無い・空なら ValueError（説明の無い検査を表に載せない）。"""
    doc = (check.__doc__ or "").strip()
    if not doc:
        raise ValueError(
            f"検査 '{_name(check)}' に docstring が無い。1 行目が {DOC_REL} の要約になるので必ず書くこと（doc_sync）"
        )
    return doc.splitlines()[0].strip()


def _escape_cell(text: str) -> str:
    """Markdown 表のセルに入れる文字列を安全にする（`|` は列の区切りなので打ち消す）。"""
    return text.replace("|", r"\|")


def _invariant_checks() -> list[Callable[[Path], list[pm.Problem]]]:
    """中核の検査の一覧（実行時 import＝checks → doc_sync の循環を避ける）。"""
    from harness import checks

    return list(checks.INVARIANT_CHECKS)


def _levels() -> tuple[str, ...]:
    from harness import checks

    return checks.LEVELS


def _commands(root: Path) -> list[tuple[str, list[str]]]:
    """`checks.toml` の (段階, コマンド) を段階の順に並べて返す。ファイルが無ければ空（複製直後でも生成できる）。"""
    path = root / "checks.toml"
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, list[str]]] = []
    for level in _levels():
        for cmd in data.get(level, {}).get("commands", []):
            out.append((level, list(cmd)))
    return out


def render(root: Path) -> str:
    """`docs/core.md` の自動生成節の本文（マーカーは含まない）を組み立てる。LF 終端。"""
    lines: list[str] = [
        HEADING_CHECKS,
        "",
        "段階（fast/standard/full）によらず毎回走る。プロファイルの検査は",
        "`.harness/config.toml` の `profiles` から実行時に加わるので、この表には載らない（各プロファイルの",
        "正本ドキュメントを見る）。",
        "",
        "| 検査 | 何を見るか |",
        "| --- | --- |",
    ]
    lines.extend(f"| `{_name(check)}` | {_escape_cell(_summary(check))} |" for check in _invariant_checks())
    lines += [
        "",
        HEADING_COMMANDS,
        "",
        "段階は累積する（full は fast・standard のコマンドも走らせる）。",
        "",
        "| 段階 | コマンド |",
        "| --- | --- |",
    ]
    # shlex.join：空白を含む引数（`-m "unit and not slow"`）を引用する＝表からそのままコピーして貼れる。
    lines.extend(f"| `{level}` | `{shlex.join(cmd)}` |" for level, cmd in _commands(root))
    return "\n".join(lines) + "\n"


def _read(path: Path) -> str:
    """本文を読む。`Path.read_text` は universal newlines で開くので、CRLF の作業ツリーでも改行は LF になる
    （＝比較の前に改行を正規化する必要はない。書き出し側は `newline="\\n"` で LF を固定する）。"""
    return path.read_text(encoding="utf-8")


def _split(text: str) -> tuple[str, str, str]:
    """マーカーの前・間・後に分ける。ちょうど 1 組でなければ ValueError。"""
    if text.count(MARKER_BEGIN) != 1 or text.count(MARKER_END) != 1:
        raise ValueError(
            f"自動生成の開始・終了マーカーがちょうど 1 組ではない"
            f"（開始 {text.count(MARKER_BEGIN)} 個・終了 {text.count(MARKER_END)} 個）"
        )
    begin = text.index(MARKER_BEGIN)
    end = text.index(MARKER_END)
    if end < begin:
        raise ValueError("自動生成の終了マーカーが開始マーカーより前にある")
    return text[:begin], text[begin + len(MARKER_BEGIN) : end], text[end + len(MARKER_END) :]


def _expected_middle(root: Path) -> str:
    """マーカーの間に入るべき正しい本文（開始マーカー直後の改行を含む）。"""
    return "\n" + render(root)


def sync(root: Path) -> bool:
    """`docs/core.md` の自動生成節を書き直す。書き換えが起きたら True（すでに最新なら False＝冪等）。"""
    path = root / DOC_REL
    if not path.is_file():
        raise ValueError(f"{DOC_REL} が無い（自動生成節を持つ中核の正本ドキュメントを先に作ること）")
    original = _read(path)
    before, _middle, after = _split(original)
    updated = f"{before}{MARKER_BEGIN}{_expected_middle(root)}{MARKER_END}{after}"
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def run_checks(root: Path) -> list[pm.Problem]:
    """中核の正本ドキュメントの自動生成節が最新か検査する。古い・マーカー異常＝error。"""
    path = root / DOC_REL
    if not path.is_file():
        return []  # 削除の検出は doclint（AGENTS.md からの参照が死にリンクになる）に委ねる
    try:
        _before, middle, _after = _split(_read(path))
    except ValueError as exc:
        return [pm.Problem("error", f"{DOC_REL}: {exc}")]
    if middle != _expected_middle(root):
        return [
            pm.Problem(
                "error",
                f"{DOC_REL}: 自動生成の節が INVARIANT_CHECKS・checks.toml の現状と食い違う"
                f"（`uv run doc-sync` で作り直す。手で書き換えない）",
            )
        ]
    return []
