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
from datetime import date, datetime
from pathlib import Path

from harness import pm
from harness.deliver.overlay import OVERLAY_PATH
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


def commit_of(root: Path, ref: str = "HEAD") -> str | None:
    """その参照が指すコミット（短い形）。git が無い・参照が無ければ None。"""
    return _git(root, "rev-parse", "--short", ref)


def label_for(root: Path, ref: str) -> str:
    """過去の時点を刻むときの表記。タグ名だけでは足りない（タグは後から動かせる・消せる）ので、
    指しているコミットを併記して、後から必ず同じ中身に辿り着けるようにする。"""
    resolved = commit_of(root, ref)
    return f"{ref}（{resolved}）" if resolved else ref


def is_dirty(root: Path) -> bool:
    """WBS の**入力**に未コミットの変更があるか（git が無ければ「無い」とみなす）。

    作業ツリー全体を見ると、生成物やメモを 1 つ置いただけで出力が拒否され、しかも「下書き」の刻印が
    嘘になる（入力は全部コミット済みなのに下書き扱い）。由来が実際に主張している範囲＝作業単位の木と
    上書きファイルだけを見る。
    """
    status = _git(root, "status", "--porcelain", "--", pm.WORK_DIR, OVERLAY_PATH)
    return bool(status)


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day is not None else None


def tree_fingerprint(wbs: Wbs) -> str:
    """この WBS を作った値そのものの指紋（同じ値からは必ず同じになる）。

    生成物どうしを突き合わせるときに、コミットが同じでも中身が違う／コミットが違っても中身は同じ、を
    見分けられるようにする。並べる値は**表に出ている値の全部**（導出後）にする＝担当・工数・実績日・
    マイルストーン・進捗・出来事のどれか 1 つでも変われば指紋が変わる（担当だけ差し替えた版が同じ指紋に
    ならないようにする）。`late` は基準日から導く値なので入れない（生成日は別の欄で刻む）。
    """
    payload = {
        "rows": [
            {
                "code": row.code,
                "ref": row.ref,
                "name": row.name,
                "status": row.status.value if row.status else None,
                "start": _iso(row.start),
                "due": _iso(row.due),
                "team": row.team,
                "assignees": list(row.assignees),
                "workdays": row.workdays,
                "actual_start": _iso(row.actual_start),
                "actual_finish": _iso(row.actual_finish),
                "milestone": row.milestone,
                "done_leaves": row.done_leaves,
                "total_leaves": row.total_leaves,
            }
            for row in wbs.walk()
        ],
        # 出来事（定例など）はガント上部のレーンとして表に出るので、開催日の集合まで指紋に含める。
        "events": [
            {
                "id": event.id,
                "name": event.name,
                "lane": event.lane,
                "occurrences": [d.isoformat() for d in event.occurrences],
            }
            for event in wbs.overlay.events
        ],
    }
    return input_fingerprint(payload)[:12]


def stamp(root: Path, wbs: Wbs, *, generated_at: datetime, commit: str | None = None) -> str:
    """生成物の見出しに出す由来の 1 行。

    `commit` を渡すとそれを使う（過去の時点を出し直すときは、いまの HEAD でなくその時点を刻む＝
    刻んだコミットと中身が食い違わない）。
    """
    where = commit or commit_of(root) or "不明"
    return f"コミット {where}　生成 {generated_at.strftime('%Y-%m-%d %H:%M')}　内容 {tree_fingerprint(wbs)}"
