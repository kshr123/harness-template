"""画面からの操作を 1 手だけ戻すための、サーバ内メモリの逆操作スタック（Ctrl+Z）。

編集・追加・削除はどれも即ファイルへ書く（1〜数行の行差し替え）。取り消しは、その操作が触ったファイルの
**操作前の本文**を覚えておき、書き戻すだけにする＝逆差分もまた元操作のバイト単位の逆＝1〜数行に収まるので、
差分だけを見る独立レビューが成り立つ状態を壊さない。

守り：
- **記録はディスクに残さない**（プロセス内メモリのみ）。生成ビューに影の状態ファイルを作らないため。
  サーバが終われば消える＝それより古い取り消しは git の領分、と境界を明示する。
- **書き戻す前に指紋を照合**する（操作の後に別の手＝エディタ・エージェント・git が正本を動かしていたら、
  推測で部分適用せずに打ち切る）。照合はサーバ側（`server._undo`）が行う。
- 段数は上限つき（deque）。redo は持たない（戻しすぎたらもう一度操作する方が、redo の整合管理より安い）。

記録の仕組み：書き込む関数は、ファイルを変える**直前**に `record(path)` を呼ぶ。記録中でなければ何もしない
（試験・生成物の書き出しなど、サーバ以外の経路では無効）。サーバは 1 操作を `recording()` で囲み、成功したら
`finalize()` の作った 1 手をスタックへ積む。1 人用のローカルサーバで、書き込みは editor.LOCK の下で 1 本ずつ
走るので、現在の記録係は 1 つ（モジュール変数）で足りる。
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType


def file_digest(path: Path) -> str | None:
    """ファイルの指紋（無ければ None）。editor.file_digest と同じ計算だが、循環 import を避けて持つ。"""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class FileState:
    """1 ファイルの、操作前の本文と操作後の指紋。"""

    path: Path
    before: str | None  # None＝操作前は存在しなかった（追加の逆＝削除）
    digest_after: str | None  # None＝操作後は存在しない（削除の逆＝復元）


@dataclass(frozen=True)
class UndoEntry:
    """1 操作ぶんの取り消し情報（画面に出す名前と、触ったファイルの一覧）。"""

    label: str
    files: list[FileState]


class Recorder:
    """1 操作が触ったファイルの「操作前の本文」を集める。"""

    def __init__(self) -> None:
        self._before: dict[Path, str | None] = {}

    def touch(self, path: Path) -> None:
        """変更する直前に呼ぶ。同じファイルを複数回触っても、いちばん最初の本文だけを残す。"""
        if path not in self._before:
            self._before[path] = path.read_text(encoding="utf-8") if path.is_file() else None

    def finalize(self, label: str) -> UndoEntry:
        """操作後の指紋を採って 1 手にまとめる（書き込みが済んだ後・まだ錠の中で呼ぶ）。"""
        files = [FileState(p, before, file_digest(p)) for p, before in self._before.items()]
        return UndoEntry(label, files)


_current: Recorder | None = None


def record(path: Path) -> None:
    """ファイルを変える直前のフック。記録中でなければ何もしない。"""
    rec = _current
    if rec is not None:
        rec.touch(path)


class recording:
    """`with` で記録を始める（サーバ層が 1 操作を囲む）。抜けると記録係を外す。"""

    def __enter__(self) -> Recorder:
        global _current
        self.rec = Recorder()
        _current = self.rec
        return self.rec

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        global _current
        _current = None


class UndoStack:
    """逆操作の山（上限つき・redo なし）。"""

    def __init__(self, limit: int = 20) -> None:
        self._items: deque[UndoEntry] = deque(maxlen=limit)

    def push(self, entry: UndoEntry) -> None:
        if entry.files:  # 触ったファイルが無い操作は積まない（戻すものが無い）
            self._items.append(entry)

    def peek(self) -> UndoEntry | None:
        return self._items[-1] if self._items else None

    def pop(self) -> None:
        if self._items:
            self._items.pop()

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
