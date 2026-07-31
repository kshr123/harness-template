"""ID・プレースホルダ・語境界の文法を 1 か所に集める（lintkit の共有部品）。

今まで各 lint（doclint・doc_source_lint・conventions・code_doc_lint…）が同じ正規表現を少しずつ違う方言で
持っていた（`ISS-\\d+` は 4 か所、プレースホルダ `XXXX|0000` は 2 か所、語境界も 3 方言）。ここに 1 度だけ
定義してテストも 1 度だけにする＝新しい検査を足すときはここを使い回す（機構あたりの意味を上げる）。
"""

from __future__ import annotations

import re

# 一時単位への参照（複製で消える／置き換わるので、恒久資産が設計の根拠に参照してはいけない対象）。
WORK_REF_RE = re.compile(r"work/(?:EP|T|E|INV)-[0-9A-Za-z-]+")  # work/ パス（プレースホルダ `work/<…>` は当たらない）
ISS_REF_RE = re.compile(r"ISS-\d+")  # 課題 ID（角括弧の `ISS-<番号>` は数字が続かないので当たらない）
LEARNING_REF_RE = re.compile(r"\bL-\d{3}\b")  # 気づき ID（docs/learnings.md の L-###。定義元は案件領域）

# 型録の説明用連番（`ISS-XXXX`・`ISS-0000`）はプレースホルダ＝実在参照でない。
PLACEHOLDER_RE = re.compile(r"XXXX|0000", re.IGNORECASE)

# ドメイン ID の一般形（接頭辞-番号）。ISS は config（issues.backend）で置き場が決まるので置き場表とは別に持つ。
ID_HOMES: dict[str, str] = {"REQ": "docs/requirements", "DEC": "docs/decisions"}
ID_PREFIXES = ("ISS", *ID_HOMES)
ID_REF_RE = re.compile(rf"\b({'|'.join(ID_PREFIXES)})-(\d+)\b")

# 素の名前（`models.py`・`retraction_lint` など）を語として拾う語境界。直前は英数・`_`・パス構成文字を禁じ、
# 直後は英数を禁じる（`pipeline.py` が `pipeline.pyi` に一致しない）。code_doc_lint 由来。
NAME_BEFORE = r"(?<![0-9A-Za-z_./-])"
NAME_AFTER = r"(?![0-9A-Za-z])"


def is_placeholder(text: str) -> bool:
    """型録の説明用連番（XXXX・0000）を含むか＝実在参照でなくプレースホルダか。"""
    return PLACEHOLDER_RE.search(text) is not None


def word_bounded(name: str) -> re.Pattern[str]:
    """素の名前を「独立した語」として一致させるパターン（前後を語境界で挟む）。

    `re.escape` するので `.`（`models.py` の拡張子など）も安全。別モジュールへのパスに名前が含まれるだけの
    一致（`ds/models.py` の中の `models.py`）は直前が `/` なので当たらない。
    """
    return re.compile(NAME_BEFORE + re.escape(name) + NAME_AFTER)


def temp_unit_refs(line: str) -> list[str]:
    """1 行から一時単位への参照（work/ パス・ISS ID・気づき ID）を集める。プレースホルダ連番は除く。"""
    found: list[str] = [m.group(0) for m in WORK_REF_RE.finditer(line)]
    found.extend(m.group(0) for m in ISS_REF_RE.finditer(line) if not is_placeholder(m.group(0)))
    found.extend(m.group(0) for m in LEARNING_REF_RE.finditer(line))
    return found
