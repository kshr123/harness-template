"""編集の場（正本から切り離した作業用の写し）と、確定したときの取り込み。

**画面からの編集は正本を直接書かない。** `.harness/wbs-edit/tree/` に入力（`work/**` と `docs/wbs.yaml`）の
写しを作り、サーバはそこだけを読み書きする。正本へは「取り込む」操作のときだけ、まとめて書く。

こうする理由：

- **別の書き手と衝突しない**。1 操作ごとに正本を書いていると、同じ木でコミットする手（人・エージェント・git）と
  ぶつかる。正本に触るのが取り込みの 1 点だけになれば、衝突する窓がそこだけになる。
- **途中経過が正本に残らない**。試しに動かした日程が、確定していないのに正本になることがない。
- **差分だけを見る独立レビューに、まとまりとして渡せる**。1 回の取り込み＝1 コミット候補。

**第 2 の正本ではない**ことを構造で言う：(a) 正本の消費者（`status`・`verify`・`task-lint`・`wbs export`・
`wbs diff`）は誰もこの写しを読まない（読む口が無い）、(b) `.gitignore` に入れてコミットできない（常在検査で
保証）、(c) `session.json` が「どの正本の状態から写したか」を指紋で持つ。エディタの未保存バッファに当たる。

書き込み系（`editor`・`adder`・`remover`）はどれも `root: Path` を受け取るので、**写しの根を渡すだけで
無改修のまま編集の場になる**（行単位の置換・書く前後の検査・Ctrl+Z もそのまま効く）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from harness import pm
from harness.deliver.editor import LOCK, EditRejected
from harness.deliver.overlay import OVERLAY_PATH

# 編集の場の置き場（git の対象外。案件の正本と同じ木の中だが、コミットできない）。
SESSION_DIR = Path(".harness/wbs-edit")
TREE = "tree"
STATE = "session.json"


def _digest(path: Path) -> str:
    """ファイルの指紋（無ければ空文字＝「その時点で存在しない」）。"""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_of(root: Path) -> list[str]:
    """WBS の入力になるファイル（正本からの相対パス）。これだけを写す・これだけを取り込む。"""
    out = [str(p.relative_to(root)) for p in sorted((root / pm.WORK_DIR).rglob("*")) if p.is_file()]
    if (root / OVERLAY_PATH).is_file():
        out.append(str(OVERLAY_PATH))
    return out


def digests_of(root: Path, paths: list[str]) -> dict[str, str]:
    """その並びのファイルの指紋（存在しないものは空文字）。"""
    return {rel: _digest(root / rel) for rel in paths}


@dataclass(frozen=True)
class Session:
    """編集の場ひとつ。`tree` が写しの根で、`base` が写した時点の**正本**の指紋。"""

    root: Path  # 正本の根
    tree: Path  # 写しの根（サーバはここだけを読み書きする）
    base: dict[str, str]  # 写した時点の正本の指紋（path → sha256）
    started: str

    @property
    def state_path(self) -> Path:
        return self.root / SESSION_DIR / STATE

    def changed(self) -> list[str]:
        """写しの側で変わったファイル（追加・変更・削除）。"""
        paths = sorted(set(self.base) | set(inputs_of(self.tree)))
        return [rel for rel in paths if _digest(self.tree / rel) != self.base.get(rel, "")]

    def drifted(self) -> list[str]:
        """**自分が変えたファイル**のうち、正本が別の手で動いてしまったもの。"""
        return [rel for rel in self.changed() if _digest(self.root / rel) != self.base.get(rel, "")]

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"base": self.base, "started": self.started, "pid": os.getpid()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _copy_inputs(root: Path, tree: Path) -> None:
    """入力だけを写す（生成物・メモは写さない＝取り込みの対象を入力に限る）。"""
    if tree.exists():
        shutil.rmtree(tree)
    for rel in inputs_of(root):
        target = tree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)


def open_session(root: Path, *, fresh: bool = False, now: datetime | None = None) -> Session:
    """編集の場を開く（書きかけがあれば続きから、無ければ正本から写し直す）。

    `fresh` を立てると書きかけを捨てて写し直す。サーバが落ちても写しはディスクに残るので、開き直せば続きから
    直せる（放っておかれて自分で終わったときも同じ）。
    """
    tree = root / SESSION_DIR / TREE
    state = root / SESSION_DIR / STATE
    if not fresh and tree.is_dir() and state.is_file():
        saved = json.loads(state.read_text(encoding="utf-8"))
        session = Session(root=root, tree=tree, base=dict(saved["base"]), started=str(saved["started"]))
        if session.changed():  # 書きかけがある＝続きから
            return session
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    _copy_inputs(root, tree)
    session = Session(root=root, tree=tree, base=digests_of(root, inputs_of(root)), started=stamp)
    session.save()
    return session


def discard(session: Session, *, now: datetime | None = None) -> Session:
    """編集の場を捨てて、いまの正本から写し直す。"""
    return open_session(session.root, fresh=True, now=now)


def confirm_token(session: Session) -> str:
    """取り込みの確認用の合図（変える対象の「正本の今」と「写しの今」を束ねた指紋）。

    画面に差分を出してから確定するまでの間に正本が動いたら、この合図が変わる＝黙って別の土台へ書かない。
    """
    parts = [f"{rel}:{_digest(session.root / rel)}:{_digest(session.tree / rel)}" for rel in session.changed()]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _project(session: Session, into: Path) -> None:
    """「正本の今 ＋ 写しで変えたぶん」を重ねた木を作る（取り込んだ後の姿を、書く前に検査するため）。"""
    for rel in inputs_of(session.root):
        target = into / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(session.root / rel, target)
    for rel in session.changed():
        target = into / rel
        if not (session.tree / rel).is_file():
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(session.tree / rel, target)


def apply(session: Session, *, today: date, confirm: str = "", now: datetime | None = None) -> list[str]:
    """写しの変更を正本へまとめて書き、書いたファイルの並びを返す。

    3 つ全部を通ってから初めて書く（どれか 1 つでも欠けたら**1 バイトも書かない**）：
    1. 変える対象の正本が、写した時点から動いていないこと（別の手が触っていたら打ち切る）。
    2. 取り込んだ後の姿を先に組み立てて検査し、**増えた指摘**が無いこと。
    3. 画面に差分を出したときと同じ土台であること（`confirm`）。
    """
    from harness.deliver.wbs_lint import all_problems

    with LOCK:
        changed = session.changed()
        if not changed:
            raise EditRejected("取り込む変更が無い")
        drifted = session.drifted()
        if drifted:
            raise EditRejected("写しを取った後に正本が別の手で動いている（取り込まなかった）: " + "、".join(drifted))
        if confirm and confirm != confirm_token(session):
            raise EditRejected("差分を出した後に正本が動いた。もう一度差分を確かめてからにする")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            projected = Path(tmp) / "projected"
            _project(session, projected)
            before = {p.message for p in all_problems(session.root, today=today) if p.level == "error"}
            introduced = [
                p for p in all_problems(projected, today=today) if p.level == "error" and p.message not in before
            ]
            if introduced:
                raise EditRejected("　/　".join(p.message for p in introduced))

        for rel in changed:
            target = session.root / rel
            source = session.tree / rel
            if not source.is_file():  # 写しで消したものは正本からも消す
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        # 取り込んだので、写しの土台は「いまの正本」になる（続けて編集できる）。
        fresh = Session(
            root=session.root,
            tree=session.tree,
            base=digests_of(session.root, inputs_of(session.root)),
            started=session.started,
        )
        fresh.save()
        return changed


def row_changes(before: object, after: object) -> list[str]:
    """取り込むと**行が**どう変わるかを 1 行ずつの日本語にする（ファイルの生差分とは別の、読む方の差分）。

    合意した計画との差（`wbs diff`）は git の参照を土台にするが、取り込みの前に見たいのは「いまの正本」との
    差なので、ここは参照を持たない純粋な突き合わせにする。見る値は表に出ている値そのもの。
    """
    watched = ("name", "status", "start", "due", "team", "assignees", "milestone")

    def rows(wbs: object) -> dict[str, object]:
        return {row.ref or row.code: row for row in wbs.walk()}  # type: ignore[attr-defined]

    old, new = rows(before), rows(after)
    out: list[str] = []
    for ref in sorted(set(old) | set(new)):
        if ref not in old:
            out.append(f"{ref} {getattr(new[ref], 'name', '')}: 追加された")
            continue
        if ref not in new:
            out.append(f"{ref} {getattr(old[ref], 'name', '')}: 消された")
            continue
        for field in watched:
            was, now_ = getattr(old[ref], field, None), getattr(new[ref], field, None)
            if was != now_:
                out.append(f"{ref} {getattr(new[ref], 'name', '')}: {field} {was} → {now_}")
    return out
