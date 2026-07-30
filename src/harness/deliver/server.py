"""編集面のローカルサーバ（`uv run wbs edit` の実体）。

画面は閲覧用と同じ描き方で作る（`render.render_html(..., editable=True)`）。違うのは、直せる欄に
書き戻し先の目印が付くことと、保存の口（`POST /edit`）があることだけ。**保存に成功したら画面を作り直す**
＝日数・ロールアップ・進捗・遅れは導出値なので、画面側で計算をやり直すと計算が 2 か所になる。導出は
サーバの 1 か所に置いたまま、毎回まるごと描き直す。

書き込みの口を開けるので、次の 3 つで守る（どれも標準的な作法で、自前の HTTP 実装は書かない）:

- **合言葉**は起動のたびに作り、画面の本文に埋めて独自ヘッダで送らせる（URL に載せない＝プロセス一覧・
  ブラウザの履歴に残らない）。独自ヘッダは、別のサイトの画面から素の form で送れない＝取り違え要求を弾く。
- **名乗ったホスト名**を検査する（攻撃者のドメインが 127.0.0.1 に解決されて同一生成元として叩かれるのを防ぐ）。
- **待ち受けは 127.0.0.1 だけ**。一定時間触られなければ自分で終わる（消し忘れを残さない）。

fastapi は当プロファイルの extra（`uv sync --extra deliver`）。このモジュールの top で import してよい
（`profile.py`・`__init__.py` からは辿られないので、軽い取り込みを壊さない）。
"""

from __future__ import annotations

import secrets
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from harness import pm
from harness.deliver import history, render
from harness.deliver import session as session_mod
from harness.deliver import wbs as wbs_mod
from harness.deliver.adder import add_child, add_milestone, add_sibling
from harness.deliver.editor import LOCK, EditRejected, apply_cascade, apply_edit
from harness.deliver.events import EventInput, remove_event, upsert_event
from harness.deliver.overlay import EVENT_ID_PREFIX
from harness.deliver.remover import remove
from harness.deliver.wbs_lint import all_problems

# 名乗ってよいホスト（ポートは切り落として比べる）。これ以外は拒否する。
ALLOWED_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


def new_token() -> str:
    """起動のたびに作る合言葉。"""
    return secrets.token_urlsafe(24)


def host_is_allowed(header: str | None) -> bool:
    """`Host` ヘッダが手元を指しているか（ポートは無視する）。名乗りが無ければ拒否する。"""
    if not header:
        return False
    host = header.rsplit(":", 1)[0] if header.count(":") == 1 else header
    return host in ALLOWED_HOSTS


class Idle:
    """最後に触られた時刻を持ち、放っておかれたかを答える（時刻は外から渡す＝試験できる）。"""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._last = 0.0
        self._lock = threading.Lock()

    def touch(self, now: float) -> None:
        with self._lock:
            self._last = now

    def expired(self, now: float) -> bool:
        with self._lock:
            return now - self._last >= self.timeout_seconds


class RemoveRequest(BaseModel):
    """`POST /remove` の本文。ref は消す行（作業単位 ID または手動行 ID）。"""

    model_config = ConfigDict(extra="forbid")

    ref: str


class AddRequest(BaseModel):
    """`POST /add` の本文。`where` が足す向き（いちばん上の階層／この行の中／上／下）。"""

    model_config = ConfigDict(extra="forbid")

    ref: str | None = None  # 基準にする行（top のときは不要）
    where: Literal["top", "child", "above", "below"] = "top"
    milestone: bool = False  # マイルストーン（期間ゼロの印）として足すか


class EditRequest(BaseModel):
    """`POST /edit` の本文。base は画面がその行を読んだ時点のファイルの指紋。"""

    model_config = ConfigDict(extra="forbid")

    ref: str
    field: str
    value: str
    base: str = ""


class ApplyRequest(BaseModel):
    """`POST /apply` の本文。confirm は差分を見せた時点の土台の合図（ずれていたら断る）。"""

    model_config = ConfigDict(extra="forbid")

    confirm: str = ""


class EventRequest(BaseModel):
    """`POST /event` の本文。id 空＝新規。開催日は dtstart+rrule と rdate/exdate（RFC 5545）で持つ。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    lane: str
    id: str = ""
    dtstart: date | None = None
    rrule: str = ""
    rdate: list[date] = []
    exdate: list[date] = []


class CascadeRequest(BaseModel):
    """`POST /cascade` の本文。ref の配下の末端すべてにその値を書く（上位の行は値を持たない）。"""

    model_config = ConfigDict(extra="forbid")

    ref: str
    field: str
    value: str


class MilestoneRequest(BaseModel):
    """`POST /milestone` の本文。マイルストーンのレーンのクリックから、その日の節目を 1 つ作る。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    due: date


def _prune_empty_dirs(start: Path, root: Path) -> None:
    """空になったフォルダを下から順に片づける（`work/` の中だけ。`work/` 自身は残す）。

    取り消しで追加を消すとき、分解でできたフォルダが空で残るのを防ぐ。docs/ 等は触らない
    （手動行の上書きは復元でも中身の書き戻しだけ＝フォルダは消えない）。
    """
    work = root / pm.WORK_DIR
    here = start
    while here != work and work in here.parents and here.is_dir() and not any(here.iterdir()):
        parent = here.parent
        here.rmdir()
        here = parent


def _write_state(path: Path, content: str | None, root: Path) -> None:
    """1 ファイルをその状態へ戻す（None＝存在しなかった→消す・空フォルダも片づける）。"""
    if content is None:
        path.unlink(missing_ok=True)
        _prune_empty_dirs(path.parent, root)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _place(root: Path, payload: AddRequest, *, today: date) -> str:
    """足す向きに応じて置き場を決める（画面が持っている「どこへ」をそのまま実行する）。"""
    if payload.where == "top":
        return add_child(root, None, today=today, milestone=payload.milestone)
    if payload.ref is None:
        raise EditRejected("どの行を基準にするか指定されていない")
    if payload.where == "child":
        return add_child(root, payload.ref, today=today, milestone=payload.milestone)
    return add_sibling(root, payload.ref, above=payload.where == "above", today=today, milestone=payload.milestone)


def create_app(root: Path, *, today: date, token: str, idle: Idle | None = None, fresh: bool = False) -> FastAPI:
    """編集面のアプリを作る。`today` は明示引数（遅れの判定の基準日を呼ぶ側が決める）。

    **書き込み先は正本ではなく、編集の場（作業用の写し）**。正本へは「取り込む」ときだけまとめて書く
    （`session.py`）。だから編集の途中で正本は 1 バイトも変わらず、同じ木でコミットする手ともぶつからない。
    """
    app = FastAPI(title="WBS 編集", docs_url=None, redoc_url=None, openapi_url=None)
    edit = session_mod.open_session(root, fresh=fresh)
    live = edit.tree  # 直す・足す・消すの宛先はすべてこの写し
    watch = idle if idle is not None else Idle(timeout_seconds=3600.0)
    watch.touch(time.monotonic())
    undo = history.UndoStack(limit=20)  # 取り消しの山（このプロセスの間だけ・redo なし）

    def _run(op: Any, label: str) -> None:  # noqa: ANN401  各書き込み操作を記録つきで実行する
        """1 操作を記録つきで走らせ、成功したら取り消しの 1 手を積む（すべて同じ錠の中で）。"""
        with LOCK, history.recording() as rec:
            op()
            undo.push(rec.finalize(label))

    @app.middleware("http")
    async def _guard(request: Request, call_next: Any) -> Any:  # noqa: ANN401  fastapi の中継関数
        if not host_is_allowed(request.headers.get("host")):
            return HTMLResponse("このホスト名では受け付けない", status_code=400)
        watch.touch(time.monotonic())
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def _page() -> HTMLResponse:
        """今の正本から画面を作り直して返す（画面は状態を持たない）。"""
        built = wbs_mod.build(live, today=today)
        return HTMLResponse(render.render_html(built, editable=True, token=token))

    def _check_token(x_wbs_token: str | None) -> None:
        if not x_wbs_token or not secrets.compare_digest(x_wbs_token, token):
            raise HTTPException(status_code=403, detail="合言葉が違う")

    @app.post("/edit")
    def _edit(payload: EditRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """1 か所を正本へ書き戻す。拒否の理由はそのまま画面に出す（黙って無視しない）。"""
        _check_token(x_wbs_token)
        out: dict[str, str] = {}

        def op() -> None:
            out["digest"] = apply_edit(
                live, ref=payload.ref, field=payload.field, value=payload.value, base_digest=payload.base, today=today
            )

        try:
            _run(op, f"{payload.ref} の {payload.field} を編集")
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return out

    @app.post("/cascade")
    def _cascade(payload: CascadeRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, int]:
        """上位の行から配下の末端をまとめて変える（書くのは末端の正本だけ＝上位に値を持たせない）。"""
        _check_token(x_wbs_token)
        out: dict[str, int] = {}

        def op() -> None:
            out["changed"] = apply_cascade(live, ref=payload.ref, field=payload.field, value=payload.value, today=today)

        try:
            _run(op, f"{payload.ref} の配下をまとめて変更")
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return out

    @app.post("/add")
    def _add(payload: AddRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """作業単位を 1 つ足す（正本＝work/ にファイルを作る。WBS 側には何も持たない）。"""
        _check_token(x_wbs_token)
        out: dict[str, str] = {}

        def op() -> None:
            out["id"] = _place(live, payload, today=today)

        try:
            _run(op, "行を追加")
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return out

    @app.post("/remove")
    def _remove(payload: RemoveRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """行を 1 つ消す（正本から取り除く）。配下を持つ単位はまとめて消さない。出来事は events から消す。"""
        _check_token(x_wbs_token)
        if payload.ref.startswith(EVENT_ID_PREFIX):
            op = lambda: remove_event(live, payload.ref, today=today)  # noqa: E731
        else:
            op = lambda: remove(live, payload.ref, today=today)  # noqa: E731
        try:
            _run(op, f"{payload.ref} を削除")
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ref": payload.ref}

    @app.post("/event")
    def _event(payload: EventRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """出来事（定例など）を足す（id 空）／直す（id 指定）。書き戻し先は docs/wbs.yaml の events。"""
        _check_token(x_wbs_token)
        out: dict[str, str] = {}
        inp = EventInput(
            name=payload.name,
            lane=payload.lane,
            id=payload.id,
            dtstart=payload.dtstart,
            rrule=payload.rrule or None,
            rdate=tuple(payload.rdate),
            exdate=tuple(payload.exdate),
        )

        def op() -> None:
            out["id"] = upsert_event(live, inp, today=today)

        try:
            _run(op, f"出来事「{payload.name}」を{'直す' if payload.id else '追加'}")
        except (EditRejected, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return out

    @app.post("/milestone")
    def _milestone(payload: MilestoneRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """マイルストーン（節目）を 1 つ足す（正本＝work/ 直下に milestone: true の作業単位を作る）。

        出来事（定例）が docs/wbs.yaml に載るのと対称に、マイルストーンは木に載せる（完了を追う対象だから）。
        """
        _check_token(x_wbs_token)
        out: dict[str, str] = {}

        def op() -> None:
            out["id"] = add_milestone(live, name=payload.name, due=payload.due, today=today)

        try:
            _run(op, f"マイルストーン「{payload.name}」を追加")
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return out

    @app.get("/changes")
    def _changes() -> dict[str, object]:
        """取り込んでいない変更を、行の変化とファイルの生差分の両方で見せる（確定の前に必ず読む）。

        行の変化は `wbs diff`（合意した計画との差）と**同じ語彙・同じ形**で出す＝差分の見せ方を 2 つ作らない。
        """
        import difflib

        files = edit.changed()
        rows = (
            session_mod.row_changes(wbs_mod.build(root, today=today), wbs_mod.build(live, today=today)) if files else []
        )
        diffs = []
        for rel in files:
            before = (root / rel).read_text(encoding="utf-8").splitlines() if (root / rel).is_file() else []
            after = (live / rel).read_text(encoding="utf-8").splitlines() if (live / rel).is_file() else []
            diffs.append(
                {
                    "path": rel,
                    "diff": "\n".join(difflib.unified_diff(before, after, f"a/{rel}", f"b/{rel}", lineterm="")),
                }
            )
        return {
            "files": files,
            "rows": rows,
            "diffs": diffs,
            "drifted": edit.drifted(),
            "confirm": session_mod.confirm_token(edit),
        }

    @app.post("/apply")
    def _apply(payload: ApplyRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, object]:
        """編集の場の変更を正本へまとめて書く（1 回の取り込み＝1 コミット候補のまとまり）。

        自動ではコミットしない（コミットは作業単位 ID を要る人・エージェントの行為）。
        """
        nonlocal edit  # 取り込みで土台が進むので、新しいセッションを持ち直す（2 度目の apply の誤検知を防ぐ）
        _check_token(x_wbs_token)
        try:
            written, edit = session_mod.apply(edit, today=today, confirm=payload.confirm)
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"written": written}

    @app.post("/discard")
    def _discard(x_wbs_token: str | None = Header(default=None)) -> dict[str, int]:
        """編集の場を捨てて、いまの正本から写し直す（正本は変わらない）。"""
        nonlocal edit  # 写し直しで新しいセッションになるので持ち直す（古い土台を握り続けない）
        _check_token(x_wbs_token)
        with LOCK:
            dropped = len(edit.changed())
            edit = session_mod.discard(edit)
            undo.clear()
        return {"dropped": dropped}

    @app.post("/undo")
    def _undo(x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """直前の 1 操作を戻す。正本が別の手で動いていたら打ち切る（推測で部分適用しない＝fail-closed）。"""
        _check_token(x_wbs_token)
        with LOCK:
            entry = undo.peek()
            if entry is None:
                raise HTTPException(status_code=409, detail="戻す操作が無い")
            # 操作の後に正本が別の手（エディタ・エージェント・git）で動いていないかを指紋で照合する。
            for fs in entry.files:
                if history.file_digest(fs.path) != fs.digest_after:
                    undo.clear()  # 履歴が現実を記述しなくなった＝以後の取り消しも当てにならない
                    raise HTTPException(
                        status_code=409,
                        detail="操作の後に正本が別の手で動いた。画面からの取り消しは打ち切る（以後は git で戻す）",
                    )
            current = [
                (fs.path, fs.path.read_text(encoding="utf-8") if fs.path.is_file() else None) for fs in entry.files
            ]
            before = {p.message for p in all_problems(live, today=today) if p.level == "error"}
            for fs in entry.files:
                _write_state(fs.path, fs.before, live)
            introduced = [p for p in all_problems(live, today=today) if p.level == "error" and p.message not in before]
            if introduced:  # 戻すと別の矛盾ができる場合は、戻す前の状態へ書き直して断る
                for path, content in current:
                    _write_state(path, content, live)
                raise HTTPException(status_code=409, detail="　/　".join(p.message for p in introduced))
            undo.pop()
            return {"undone": entry.label}

    return app
