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

import frontmatter
import yaml

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
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise BaselineError(f"{root} は git リポジトリではない（合意した時点はタグで指すので git が要る）")
    if _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise BaselineError(f"'{ref}' という参照が無い（`git tag` で打った名前か確かめる）")
    paths = [p for p in _INPUT_PATHS if _exists_at(root, ref, p)]
    if not paths:
        raise BaselineError(f"'{ref}' の時点に work/ が無い（その時点にはまだ作業単位が無い）")
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


# 1 つの欄について遡るコミットの上限（これを超えるほど触られたファイルは、先頭だけ示せば十分）。
_MAX_HISTORY = 60


def _field_at(root: Path, commit: str, rel: str, field: str, row_id: str | None) -> str | None:
    """その時点のファイルから、その欄の値を読む（読めなければ None）。"""
    proc = _git(root, "show", f"{commit}:{rel}")
    if proc.returncode != 0:
        return None
    text = proc.stdout
    try:
        if row_id is None:
            meta = frontmatter.loads(text).metadata
            value = meta.get(field)
        else:
            raw = yaml.safe_load(text)
            rows = raw.get("rows", []) if isinstance(raw, dict) else []
            row = next((r for r in rows if isinstance(r, dict) and r.get("id") == row_id), None)
            value = row.get(field) if row else None
    except yaml.YAMLError:
        return None
    return None if value is None else str(value)


def commits_changing(root: Path, ref: str, path: Path, field: str, row_id: str | None = None) -> list[str]:
    """その時点から今までに、**その欄の値を実際に変えた**コミット（新しい順・「短い hash 件名」の形）。

    「そのファイルを触ったコミット」で代用すると、日付を動かした後に同じファイルの担当欄を直しただけの
    コミットが「日付が動いた理由」として出てしまう＝クライアントへの説明に嘘の理由が刻まれる。
    各コミットとその 1 つ前で欄の値を読み比べ、変わったものだけを返す。
    """
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    proc = _git(root, "log", "--format=%h %s", f"{ref}..HEAD", "--", rel)
    if proc.returncode != 0:
        return []
    lines = [line for line in proc.stdout.splitlines() if line.strip()][:_MAX_HISTORY]
    out: list[str] = []
    for line in lines:
        commit = line.split(" ", 1)[0]
        if _field_at(root, commit, rel, field, row_id) != _field_at(root, f"{commit}~1", rel, field, row_id):
            out.append(line)
    return out


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


# 子から導く欄（動いても「その行を直したから」ではない＝配下の変更の結果）。表題は親でも自分の値。
_DERIVED_ATTRS = frozenset({"start", "due", "status"})


def _key(row: WbsRow) -> str:
    """比較の突き合わせ鍵。作業単位・手動行は ID、顧客向けの節は名前（節は ID を持たない）。"""
    return row.ref if row.ref is not None else f"節 {row.name}"


def _rows_by_key(wbs: Wbs) -> dict[str, WbsRow]:
    """節も含めた全行（節の日程が動いたことはクライアントが最も見るところなので、落とさない）。"""
    return {_key(row): row for row in wbs.walk()}


def compare(before: Wbs, after: Wbs, *, root: Path, ref: str) -> list[Change]:
    """2 つの時点の WBS を突き合わせ、動いた点だけを並べる（動いていない単位は出てこない）。"""
    old, new = _rows_by_key(before), _rows_by_key(after)
    changes: list[Change] = []
    for key in sorted(set(old) | set(new)):
        was, now = old.get(key), new.get(key)
        if was is None and now is not None:
            changes.append(Change(key, now.name, "追加", None, None, ()))
            continue
        if now is None and was is not None:
            changes.append(Change(key, was.name, "削除", None, None, ()))
            continue
        if was is None or now is None:
            continue
        for label, attr in _COMPARED:
            old_value, new_value = _value(was, attr), _value(now, attr)
            if old_value == new_value:
                continue
            derived = bool(now.children) and attr in _DERIVED_ATTRS
            commits = () if derived else tuple(_why(root, ref, now, attr))
            changes.append(Change(key, now.name, label, old_value, new_value, commits, derived))
    return changes


def _why(root: Path, ref: str, row: WbsRow, attr: str) -> list[str]:
    """その欄の値を実際に変えたコミット（値が入っているファイルを、その時点から今まで遡って調べる）。"""
    if row.path is None:
        return []
    field = "name" if attr == "name" and row.source == "manual" else ("title" if attr == "name" else attr)
    row_id = row.ref if row.source == "manual" else None
    return commits_changing(root, ref, row.path, field, row_id)


def changes_since(root: Path, ref: str, *, today: date) -> list[Change]:
    """合意した時点（git の参照）からの変化を集める。"""
    now = build(root, today=today)
    with tree_at(root, ref) as snapshot:
        then = build(snapshot, today=today)
    return compare(then, now, root=root, ref=ref)
