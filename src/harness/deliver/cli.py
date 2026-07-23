"""deliver プロファイルの CLI 入口（typer）。`uv run wbs` で顧客向けの WBS・ガントを出す。

中核・他プロファイルの CLI とはモジュールを分ける（プロファイル境界）。祝日ライブラリ（extra deliver）が
無い環境では導入方法を案内して exit 1 する（生の ImportError の栈を吐かない）。
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from harness.deliver import baseline, formats, stamp, wbs_lint
from harness.deliver import wbs as wbs_mod
from harness.registry import render_catalog

# Windows コンソール（cp932）でも日本語・記号を出せるよう UTF-8 に固定（他プロファイルの CLI と同じ作法）。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

wbs_app = typer.Typer(help="作業単位の木から顧客向けの WBS・ガントを出す（deliver プロファイル）", add_completion=False)

DEFAULT_OUT = "artifacts/wbs/WBS"  # 拡張子は形式が決める（formats.SUFFIX）


def _fail(message: str) -> None:
    """指摘を出して止める（既定を不合格側に置く＝黙って空の成果物を出さない）。"""
    typer.echo(message, err=True)
    raise typer.Exit(1)


@wbs_app.command("export")
def _export(
    out: Annotated[Path | None, typer.Option(help=f"出力先（既定 {DEFAULT_OUT}）")] = None,
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    at: Annotated[str | None, typer.Option(help="この時点の WBS を出す（git のタグ・コミット）")] = None,
    fmt: Annotated[str, typer.Option("--format", help="出力形式（一覧は `uv run wbs formats`）")] = "html",
    draft: Annotated[bool, typer.Option("--draft", help="未コミットの変更を含んだまま下書きとして出す")] = False,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """WBS を自己完結の HTML 1 ファイルに出す（クライアントへ渡す形）。

    検査に失敗する状態・描く対象が 1 件も無い状態では出力しない（空の工程表を黙って渡さない）。
    未コミットの変更があるときも既定では出力しない（刻んだコミットが嘘になる）。`--draft` を付けたときだけ、
    下書きと分かる表示で出す。`--at` に合意した時点（タグ・コミット）を渡すと、その時点の WBS を出し直す。
    """
    base = date.fromisoformat(today) if today else date.today()
    try:
        writer = formats.RENDERERS.resolve(fmt).factory
    except ValueError as exc:
        _fail(str(exc))
        return
    if at is None:
        _export_from(root, root, out=out, today=base, draft=draft, commit=None, fmt=fmt, writer=writer)
        return
    try:
        with baseline.tree_at(root, at) as snapshot:
            _export_from(root, snapshot, out=out, today=base, draft=False, commit=at, fmt=fmt, writer=writer)
    except baseline.BaselineError as exc:
        _fail(str(exc))


@wbs_app.command("formats")
def _formats() -> None:
    """出せる形式の一覧（入れていない依存の形式はここに出ない＝選べる形式が使える形式）。"""
    render_catalog(formats.RENDERERS)


def _export_from(
    root: Path,
    source: Path,
    *,
    out: Path | None,
    today: date,
    draft: bool,
    commit: str | None,
    fmt: str,
    writer: Callable[..., None],
) -> None:
    """`source` の中身から WBS を出す（`root` は出力先と git を見る先）。過去の時点も同じ道を通る。"""
    # 例外の種類ごとに節を分ける（ruff format が `except (A, B):` を壊す既知の不具合を踏まないため）。
    try:
        built = wbs_mod.build(source, today=today)
    except ValueError as exc:  # 上書きの検証エラー（pydantic の ValidationError を含む）
        _fail(f"WBS を組み立てられない: {exc}")
        return
    except OSError as exc:  # ファイルが読めない
        _fail(f"WBS を組み立てられない: {exc}")
        return
    errors = [p for p in wbs_lint.check(source, today=today) if p.level == "error"]
    if errors:
        for problem in errors:
            typer.echo(f"error: {problem.message}", err=True)
        _fail(f"WBS の検査に {len(errors)} 件失敗した（直してから出す）")
        return
    if built.span is None:
        _fail(
            "日程（start / due）を持つ作業単位が 1 件も無い。空のガントは出さない"
            "（work/ の単位に start・due を書くか、docs/wbs.yaml に手動行を足す）"
        )
        return
    dirty = commit is None and stamp.is_dirty(root)
    if dirty and not draft:
        _fail(
            "作業ツリーに未コミットの変更がある。このまま出すと生成物に刻むコミットが実際の中身と食い違う"
            "（先にコミットする。下書きとして出すなら --draft を付ける）"
        )
        return
    target = out if out is not None else root / (DEFAULT_OUT + formats.SUFFIX.get(fmt, ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    provenance = stamp.stamp(root, built, generated_at=datetime.now(UTC).astimezone(), commit=commit)
    writer(built, target, provenance=provenance, draft=dirty)
    rows = len(built.walk())
    note = f"（未日程 {len(built.unscheduled)} 件）" if built.unscheduled else ""
    typer.echo(f"{target}: {rows} 行を出力した{note}　{provenance}")


@wbs_app.command("diff")
def _diff(
    ref: Annotated[str, typer.Argument(help="合意した時点（git のタグ・コミット。例 v1.0-agreed）")],
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """合意した時点の計画と、いまの計画の差を並べる。

    変化の理由は、その日程を動かしたコミットのメッセージをそのまま添える（理由の保管場所を新設しない）。
    合意した時点そのものの WBS を出し直したいときは `uv run wbs export --at <参照>`。
    """
    base = date.fromisoformat(today) if today else date.today()
    try:
        changes = baseline.changes_since(root, ref, today=base)
    except baseline.BaselineError as exc:
        _fail(str(exc))
        return
    if not changes:
        typer.echo(f"{ref} の時点から、計画は動いていない")
        return
    typer.echo(f"{ref} の時点からの差（{len(changes)} 件）")
    for change in changes:
        typer.echo(f"  {change.line()}")


@wbs_app.command("lint")
def _lint(
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """WBS の不変条件だけを検査する（`uv run verify` が回すのと同じ検査を単体で走らせる）。"""
    base = date.fromisoformat(today) if today else date.today()
    problems = wbs_lint.check(root, today=base)
    for problem in problems:
        typer.echo(f"{problem.level}: {problem.message}")
    if any(p.level == "error" for p in problems):
        raise typer.Exit(1)
    typer.echo("WBS の検査に成功した")


@wbs_app.command("edit")
def _edit(
    port: Annotated[int, typer.Option(help="待ち受けポート（0 で空いているものを自動で選ぶ）")] = 0,
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    idle_minutes: Annotated[float, typer.Option(help="この分数だけ触られなければ自分で終わる")] = 60.0,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """手元のブラウザで WBS を直す（書き戻す先は正本＝作業単位の frontmatter と docs/wbs.yaml）。

    待ち受けは 127.0.0.1 だけ。合言葉は起動のたびに作り、画面の本文に埋める（URL には載せない）。
    表示された URL をブラウザで開く。
    """
    base = date.fromisoformat(today) if today else date.today()
    try:
        import uvicorn

        from harness.deliver.server import Idle, create_app, new_token
    except ImportError as exc:
        typer.echo(f"fastapi/uvicorn が無い（deliver extra 未導入）。`uv sync --extra deliver` で導入する: {exc}")
        raise typer.Exit(1) from exc

    chosen = port or _free_port()
    idle = Idle(timeout_seconds=idle_minutes * 60.0)
    token = new_token()
    app = create_app(root, today=base, token=token, idle=idle)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=chosen, log_level="warning"))
    threading.Thread(target=_stop_when_idle, args=(server, idle), daemon=True).start()
    typer.echo(f"http://127.0.0.1:{chosen}/ をブラウザで開く（{idle_minutes:g} 分触らなければ自動で終わる）")
    server.run()


def _free_port() -> int:
    """空いているポートを 1 つもらう（毎回違う番号にして、他の待ち受けと衝突させない）。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_when_idle(server: Any, idle: Any) -> None:  # noqa: ANN401  uvicorn.Server / Idle（遅延取り込み）
    """放っておかれたら待ち受けを終える（消し忘れたサーバが裏で生き続けないようにする）。"""
    while not server.should_exit:
        time.sleep(5.0)
        if idle.expired(time.monotonic()):
            server.should_exit = True
            return


def wbs_main() -> None:
    """`uv run wbs` の入口。"""

    wbs_app()
