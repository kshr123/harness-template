"""GitHub Actions ワークフロー YAML を読む共有部品（lintkit）。

pyyaml は YAML 1.1 の implicit resolver で `on:` キーを bool `True` に読む。この落とし穴を 1 か所で吸収し、
`ci_lint`（ops）と `schedule_lint`（agent）が同じ読み方を共有する＝各所で True-trap を書かず drift させない。
"""

from __future__ import annotations

from typing import Any


def on_block(doc: Any) -> Any:  # noqa: ANN401  YAML は任意構造
    """workflow の `on:` ブロックを返す（pyyaml が `True` に読む鍵も見る）。dict でなければ None。"""
    if not isinstance(doc, dict):
        return None
    return doc.get("on", doc.get(True))


def trigger_names(doc: Any) -> set[str]:  # noqa: ANN401  YAML は任意構造
    """`on:` のトリガ名の集合（dict/list/str のどれでも／それ以外は空）。"""
    on = on_block(doc)
    if isinstance(on, dict):
        return {str(k) for k in on}
    if isinstance(on, list):
        return {str(v) for v in on}
    if isinstance(on, str):
        return {on}
    return set()
