"""撤回した決まりごとの残骸検査（retraction_lint）。

決まりごとは目的ではなく手段である。効かなくなった決まりごと（仕組み・識別子）を外せないなら、手段は
増える一方になる。この基盤は「気づきを記録し、価値があれば機械検査・抽象・スキル・規約のどれかに落とし込む」
という**追加の流れ**だけを設計していた。落とし込んだものを**外す流れ**が無く、撤回漏れが実在した
（DEC〔決定記録〕の仕組みは廃止されたのに識別子と参照がコード・文書・スキルに残り、後から一掃するまで
気づかれなかった）。

この検査が塞ぐのは「撤回したのに名前が残る」残骸だけ：

- 撤回した名前は撤回した時点で**有限に確定する**。これは「まだ作られていない不良の検出器」（未来の不良を
  先回りして当てにいく無理）とは異なり、**既に確定した集合が消えたことの確認**である（doclint の ID 接頭辞の
  置き場実在検査と同型）。
- 撤回した名前は `RETRACTED`（名前→いつ・なぜ外したか）に**1 か所だけ**置く。理由は必須（空は ValueError）。
- 掃除が済めば**その項目を消してよい**（残骸ゼロを一度証明したら検査は役目を終える＝一覧は増える一方でない）。
  だから空 dict＝正常（緑）。
- 撤回の**是非**（もう効いていない、という判断）は人がする。機械にはさせない。この検査は
  「撤回済みの名前が残っていないか」だけを見る。禁止語の一覧（未来の語を当てにいく無限集合）とは別物。
- 名前を挙げてよいのは 2 か所だけ：撤回一覧（このファイル）と撤回の記録（`docs/learnings.md`）。それ以外の
  資産（src/ docs/ .claude/skills/ templates/）に語境界一致で残っていたら error。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 撤回した識別子 → いつ・なぜ外したか（`docs/learnings.md` への 1 行。空文字は不可＝理由必須）。
# 掃除が済んだ項目はここから消してよい（残骸ゼロを一度証明したら検査は役目を終える）。空 dict＝正常。
RETRACTED: dict[str, str] = {}

# 残骸が残ってはいけない置き場（複製後も残る資産。work/ issues/ は一時的なので対象外）。
_SCAN_DIRS = ("src", "docs", ".claude/skills", "templates")
# 走査するテキストの拡張子（バイナリ・データ実体は見ない）。
_TEXT_SUFFIXES = frozenset({".py", ".md", ".toml", ".yaml", ".yml", ".txt", ".cfg", ".ini"})
# 撤回した名前を挙げてよい 2 か所（撤回一覧＝このファイル・撤回の記録＝learnings）。残骸検査から除く。
_ALLOWED = frozenset({"src/harness/retraction_lint.py", "docs/learnings.md"})


def _validated_retracted() -> dict[str, str]:
    """撤回一覧の理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って撤回しない・fail closed）。"""
    for name, reason in RETRACTED.items():
        if not reason.strip():
            raise ValueError(f"RETRACTED[{name!r}] の理由が空。撤回には人が読める理由（いつ・なぜ外したか）が必須")
    return RETRACTED


def run_checks(root: Path) -> list[pm.Problem]:
    """撤回済みの決まりごとの名前が、資産（src・docs・skills・templates）に残骸として残っていないか検査する。

    `RETRACTED` が空なら何もしない（撤回した名前が無い＝正常）。非空なら各名前を語境界一致で全走査し、
    撤回一覧・撤回記録（`_ALLOWED`）以外で見つかったら error（掃除するか、まだ使うなら撤回を取り消す）。
    """
    retracted = _validated_retracted()
    if not retracted:
        return []  # 撤回した名前が無い＝正常（空でも緑）
    patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in retracted}
    problems: list[pm.Problem] = []
    for rel_dir in _SCAN_DIRS:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in _TEXT_SUFFIXES):
            rel = path.relative_to(root).as_posix()
            if rel in _ALLOWED:
                continue  # 名前を挙げてよい 2 か所（撤回一覧・撤回記録）は残骸ではない
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, pattern in patterns.items():
                if pattern.search(text):
                    problems.append(
                        pm.Problem(
                            "error",
                            f"{rel}: 撤回済みの名前 '{name}' が残っている（{retracted[name]}）。掃除するか、"
                            "まだ使うなら撤回を取り消す（撤回の記録は docs/learnings.md）",
                        )
                    )
    return problems
