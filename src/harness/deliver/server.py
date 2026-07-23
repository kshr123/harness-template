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
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from harness.deliver import render
from harness.deliver import wbs as wbs_mod
from harness.deliver.editor import EditRejected, apply_edit

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


class EditRequest(BaseModel):
    """`POST /edit` の本文。base は画面がその行を読んだ時点のファイルの指紋。"""

    model_config = ConfigDict(extra="forbid")

    ref: str
    field: str
    value: str
    base: str = ""


def create_app(root: Path, *, today: date, token: str, idle: Idle | None = None) -> FastAPI:
    """編集面のアプリを作る。`today` は明示引数（遅れの判定の基準日を呼ぶ側が決める）。"""
    app = FastAPI(title="WBS 編集", docs_url=None, redoc_url=None, openapi_url=None)
    watch = idle if idle is not None else Idle(timeout_seconds=3600.0)
    watch.touch(time.monotonic())

    @app.middleware("http")
    async def _guard(request: Request, call_next: Any) -> Any:  # noqa: ANN401  fastapi の中継関数
        if not host_is_allowed(request.headers.get("host")):
            return HTMLResponse("このホスト名では受け付けない", status_code=400)
        watch.touch(time.monotonic())
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def _page() -> HTMLResponse:
        """今の正本から画面を作り直して返す（画面は状態を持たない）。"""
        built = wbs_mod.build(root, today=today)
        return HTMLResponse(render.render_html(built, editable=True, token=token))

    @app.post("/edit")
    def _edit(payload: EditRequest, x_wbs_token: str | None = Header(default=None)) -> dict[str, str]:
        """1 か所を正本へ書き戻す。拒否の理由はそのまま画面に出す（黙って無視しない）。"""
        if not x_wbs_token or not secrets.compare_digest(x_wbs_token, token):
            raise HTTPException(status_code=403, detail="合言葉が違う")
        try:
            digest = apply_edit(
                root, ref=payload.ref, field=payload.field, value=payload.value, base_digest=payload.base, today=today
            )
        except EditRejected as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"digest": digest}

    return app
