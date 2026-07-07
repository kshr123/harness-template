"""入力指紋（正準 JSON の sha256）。serve と agent が共有する中核部品（stdlib のみ＝軽い）。

`serve/runtime.py` から移設した（T-0091の二重管理排除）。serve は予測 1 行（features）、
agent は 1 実行の入力（{"input": テキスト}）の指紋に使う。agent はここから import する
（serve を import しない＝プロファイル境界）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def input_fingerprint(payload: Mapping[str, Any]) -> str:
    """入力 1 件（payload）の指紋＝正準 JSON（キー昇順・区切り最小・非 ASCII 素通し）の sha256。

    同じ payload からは必ず同じ指紋になる（監視・重複検出が行単位で照合できる）。値は JSON 由来
    である前提＝JSON にできない値はここで明示的に失敗する。
    """
    canonical = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
