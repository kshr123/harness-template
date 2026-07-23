"""合意した時点の計画と、いまの計画の差を出す。

受託では「合意した計画」が実質的な契約の一部なので、日程が動いたときに**何が・いつ・なぜ動いたか**を
説明できないと信頼に直結する。だが変更履歴の台帳を新しく作ると、書き忘れた第 1 号から嘘になる。

そこで**新しい保管場所を作らない**：

- 合意した時点＝**git のタグ（またはコミット）**。合意時に印を打つだけで、改竄できない時系列が手に入る。
- 変更の理由＝**その日程を動かしたコミットのメッセージ**。コミットメッセージの冒頭に作業単位の ID を
  書くことは既に検査（commit-msg-lint）が強制しているので、理由は既に書かれている。書き写さない。

比較は、指定した時点の `work/` と `docs/wbs.yaml` を取り出して同じ導出（`wbs.build`）にかけ、
出てきた行どうしを突き合わせる＝表示・検査・比較の 3 つが同じ導出を見る。
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from harness.deliver.overlay import OVERLAY_PATH
from harness.deliver.wbs import Wbs, WbsRow, build

# 取り出す対象＝WBS の入力になるものだけ（他のファイルは比較に関係しない）。
_INPUT_PATHS = ("work", OVERLAY_PATH)

# 比べる欄（表示名 → WbsRow の属性）。営業日数・進捗は比べない（元の値が動けば必ず動くので二重に報告しない）。
# 親の行の日程は子から導いた値だが、**比べる**：フェーズの終わりがいつ動いたかはクライアントが最も見る
# ところで、それを落とすと「タスクは動いたがフェーズは？」を人が計算し直すことになる。ただし自分で動いた
# のではないと分かるよう、配下の変更による結果であることを添える。
_COMPARED: tuple[tuple[str, str], ...] = (
    ("予定開始", "start"),
    ("予定終了", "due"),
    ("状態", "status"),
    ("表題", "name"),
)


class BaselineError(Exception):
    """指定した時点を読めない（そんな参照が無い・git が無い等）。"""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except OSError as exc:
        raise BaselineError(f"git を呼べない: {exc}") from exc
    except subprocess.SubprocessError as exc:
        raise BaselineError(f"git の呼び出しに失敗した: {exc}") from exc


def _exists_at(root: Path, ref: str, path: str) -> bool:
    """その時点にそのパスがあるか。"""
    return _git(root, "cat-file", "-e", f"{ref}:{path}").returncode == 0


@contextmanager
def tree_at(root: Path, ref: str) -> Iterator[Path]:
    """指定した時点の入力（`work/` と上書き）を一時の場所へ取り出す。

    作業ツリーを切り替えない（いまの作業を邪魔しない）。取り出したものは抜けたときに消える。
    """
    paths = [p for p in _INPUT_PATHS if _exists_at(root, ref, p)]
    if not paths:
        raise BaselineError(f"'{ref}' の時点に work/ が無い（参照が正しいか確かめる）")
    proc = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", ref, *paths],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise BaselineError(f"'{ref}' の時点を取り出せない: {proc.stderr.decode('utf-8', 'replace').strip()}")
    with tempfile.TemporaryDirectory(prefix="wbs-baseline-") as tmp:
        dest = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
            tar.extractall(dest, filter="data")  # filter="data" ＝取り出し先の外に書かせない
        yield dest


def commits_touching(root: Path, ref: str, path: Path) -> list[str]:
    """その時点から今までに、そのファイルを触ったコミット（新しい順・「短い hash 件名」の形）。"""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    proc = _git(root, "log", "--format=%h %s", f"{ref}..HEAD", "--", rel)
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


@dataclass(frozen=True)
class Change:
    """合意した時点からの変化 1 件。"""

    ref: str  # 作業単位 ID または手動行 ID
    name: str
    kind: str  # "追加" | "削除" | 比べた欄の表示名
    before: str | None
    after: str | None
    commits: tuple[str, ...] = ()  # その変化を入れたコミット（新しい順）
    derived: bool = False  # 子を持つ行＝自分で動いたのでなく、配下の変更の結果として動いた

    def line(self) -> str:
        """1 行の説明（そのまま画面に出す）。"""
        head = f"{self.ref} {self.name}"
        if self.kind == "追加":
            body = "追加された"
        elif self.kind == "削除":
            body = "削除された"
        else:
            body = f"{self.kind} {self.before or '（無し）'} → {self.after or '（無し）'}"
        if self.derived:
            return f"{head}: {body}（配下の変更による）"
        why = f"　← {self.commits[0]}" if self.commits else ""
        more = f"（他 {len(self.commits) - 1} 件のコミット）" if len(self.commits) > 1 else ""
        return f"{head}: {body}{why}{more}"


def _value(row: WbsRow, attr: str) -> str | None:
    value = getattr(row, attr)
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(getattr(value, "value", value))


def _rows_by_ref(wbs: Wbs) -> dict[str, WbsRow]:
    return {row.ref: row for row in wbs.walk() if row.ref is not None}


def compare(before: Wbs, after: Wbs, *, root: Path, ref: str) -> list[Change]:
    """2 つの時点の WBS を突き合わせ、動いた点だけを並べる（動いていない単位は出てこない）。"""
    old, new = _rows_by_ref(before), _rows_by_ref(after)
    changes: list[Change] = []
    for item_id in sorted(set(old) | set(new)):
        was, now = old.get(item_id), new.get(item_id)
        if was is None and now is not None:
            changes.append(Change(item_id, now.name, "追加", None, None, tuple(_why(root, ref, now))))
            continue
        if now is None and was is not None:
            changes.append(Change(item_id, was.name, "削除", None, None, ()))
            continue
        if was is None or now is None:
            continue
        derived = bool(now.children)
        for label, attr in _COMPARED:
            old_value, new_value = _value(was, attr), _value(now, attr)
            if old_value != new_value:
                commits = () if derived else tuple(_why(root, ref, now))
                changes.append(Change(item_id, now.name, label, old_value, new_value, commits, derived))
    return changes


def _why(root: Path, ref: str, row: WbsRow) -> list[str]:
    """その行の値が入っているファイルを、指定の時点から今までに触ったコミット。"""
    return commits_touching(root, ref, row.path) if row.path is not None else []


def changes_since(root: Path, ref: str, *, today: date) -> list[Change]:
    """合意した時点（git の参照）からの変化を集める。"""
    now = build(root, today=today)
    with tree_at(root, ref) as snapshot:
        then = build(snapshot, today=today)
    return compare(then, now, root=root, ref=ref)
