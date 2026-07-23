"""提出物に刻む由来（どのコミット・いつ・どの木から出たか）と、未コミットのときの扱い。

クライアントへ渡した紙・PDF・HTML は、後から「これはいつの計画か」を問われる。生成物の中に由来が
無いと、正本のどの時点と照合すればよいかが分からなくなる（送った側の記憶に頼ることになる）。

作業ツリーに未コミットの変更があるとき、**既定では生成を拒否する**。刻んだコミットが実際の中身と
違う＝由来が嘘になるため。定例の直前に 1 行直してすぐ出す実務はあるので、下書きとして明示したときだけ
「下書き」と分かる形で許す（既定を不合格側に置いたまま、逃げ道は見て分かる形にする）。

git が無い・リポジトリでない環境では、コミットの欄を「不明」にして拒否はしない（git を前提にしない）。
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from harness.deliver.wbs import Wbs
from harness.fingerprint import input_fingerprint


def _git(root: Path, *args: str) -> str | None:
    """git を 1 回呼ぶ（失敗・未導入・リポジトリでない、はすべて None）。ネットワークは使わない。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    except subprocess.SubprocessError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def commit_of(root: Path) -> str | None:
    """いま出ている中身の元になっているコミット（短い形）。git が無ければ None。"""
    return _git(root, "rev-parse", "--short", "HEAD")


def is_dirty(root: Path) -> bool:
    """作業ツリーに未コミットの変更があるか（git が無ければ「無い」とみなす）。"""
    status = _git(root, "status", "--porcelain")
    return bool(status)


def tree_fingerprint(wbs: Wbs) -> str:
    """この WBS を作った値そのものの指紋（同じ値からは必ず同じになる）。

    生成物どうしを突き合わせるときに、コミットが同じでも中身が違う／コミットが違っても中身は同じ、を
    見分けられるようにする。並べる値は、表に出ている値そのもの（導出後）にする。
    """
    payload = {
        "rows": [
            {
                "code": row.code,
                "ref": row.ref,
                "name": row.name,
                "status": row.status.value if row.status else None,
                "start": row.start.isoformat() if row.start else None,
                "due": row.due.isoformat() if row.due else None,
            }
            for row in wbs.walk()
        ]
    }
    return input_fingerprint(payload)[:12]


def stamp(root: Path, wbs: Wbs, *, generated_at: datetime, commit: str | None = None) -> str:
    """生成物の見出しに出す由来の 1 行。

    `commit` を渡すとそれを使う（過去の時点を出し直すときは、いまの HEAD でなくその時点を刻む＝
    刻んだコミットと中身が食い違わない）。
    """
    where = commit or commit_of(root) or "不明"
    return f"コミット {where}　生成 {generated_at.strftime('%Y-%m-%d %H:%M')}　内容 {tree_fingerprint(wbs)}"
