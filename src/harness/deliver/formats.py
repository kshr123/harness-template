"""出力形式の登録簿（`RENDERERS`）。**既定は HTML 1 つだけ**。

「同じ内容の成果物が 2 つ並んでどちらが正か分からない」状態を作らないので、既定で増やさない。
一方で不変条件は「正本 1 つ・編集面 1 つ」であって「出力形式 1 つ」ではない（`STATUS.md` や
`docs/core.md` の自動生成節と同じ形＝1 つの正本から複数のビューを出すのは元からの作法）。
先方の様式指定がある案件のために、**その依存が入っている案件でだけ**形式が生える形にしてある
（モデルの保存形式・モデル種と同じ条件登録）。入れなければ一覧にも出ないので、選べる形式＝
使える形式になる。

形式を足すときは、`write(wbs, path, *, provenance, draft)` の形の関数をここに登録するだけでよい
（導出は `wbs.py` の 1 か所にあるので、形式側は書き出すだけ）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from harness.deliver import render
from harness.deliver.wbs import Wbs
from harness.registry import Entry, Registry


@dataclass(frozen=True, kw_only=True)
class RendererEntry(Entry):
    """出力形式 1 つ。`suffix` は出力先を省いたときに付ける拡張子。

    拡張子を別の対応表に持つと、形式を足したときに片方だけ書き忘れて拡張子の無いファイルができる
    （登録簿の外に 2 つ目の台帳を作らない）。
    """

    suffix: str


RENDERERS: Registry[RendererEntry] = Registry("出力形式", catalog="wbs formats", extras_hint={"xlsx": "openpyxl"})


def _write_html(
    wbs: Wbs,
    path: Path,
    *,
    provenance: str = "",
    draft: bool = False,
    baseline: dict[str, tuple[date | None, date | None]] | None = None,
) -> None:
    """自己完結の HTML 1 ファイル（既定。外部リソースを読まないので、そのまま渡せる）。

    `baseline`（合意した時点の棒の期間・行の鍵ごと）が渡ると、現状の棒の下に淡い棒を重ねる（計画対比）。
    ベースラインを重ねられるのは HTML だけ＝他形式に `--against` を渡すと CLI が明示的に拒否する（黙って落とさない）。
    """
    path.write_text(render.render_html(wbs, provenance=provenance, draft=draft, baseline=baseline), encoding="utf-8")


RENDERERS.register("html", _write_html, entry_cls=RendererEntry, suffix=".html")

try:  # 表計算の枝（openpyxl が入っている案件でだけ生える）。核はこの形式を知らない。
    import openpyxl  # noqa: F401  入っているかを確かめるためだけの取り込み
except ImportError:
    pass
else:
    from harness.deliver.xlsx import write_xlsx

    RENDERERS.register("xlsx", write_xlsx, entry_cls=RendererEntry, suffix=".xlsx")
