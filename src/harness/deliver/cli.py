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
from typing import Annotated, Any, NoReturn

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

DEFAULT_OUT = "artifacts/wbs/WBS"  # 拡張子は形式が決める（RendererEntry.suffix）


def _fail(message: str) -> NoReturn:
    """指摘を出して止める（既定を不合格側に置く＝黙って空の成果物を出さない）。必ず送出する。"""
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _base_date(today: str | None) -> date:
    """基準日を読む。書き方が違うときは、生の例外でなく直し方を出して止める。"""
    if today is None:
        return date.today()
    try:
        return date.fromisoformat(today)
    except ValueError:
        _fail(f"基準日は YYYY-MM-DD で書く（受け取った値: {today}）")


@wbs_app.command("export")
def _export(
    out: Annotated[Path | None, typer.Option(help=f"出力先（既定 {DEFAULT_OUT}）")] = None,
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    at: Annotated[str | None, typer.Option(help="この時点の WBS を出す（git のタグ・コミット）")] = None,
    against: Annotated[
        str | None, typer.Option(help="合意した時点の棒を淡色で重ねる（HTML のみ・git のタグ・コミット）")
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="出力形式（一覧は `uv run wbs formats`）")] = "html",
    draft: Annotated[bool, typer.Option("--draft", help="未コミットの変更を含んだまま下書きとして出す")] = False,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """WBS を自己完結の HTML 1 ファイルに出す（クライアントへ渡す形）。

    検査に失敗する状態・描く対象が 1 件も無い状態では出力しない（空の工程表を黙って渡さない）。
    未コミットの変更があるときも既定では出力しない（刻んだコミットが嘘になる）。`--draft` を付けたときだけ、
    下書きと分かる表示で出す。`--at` に合意した時点（タグ・コミット）を渡すと、その時点の WBS を出し直す。
    `--against` に合意した時点を渡すと、その時点の棒を淡色で重ねる（計画対比。HTML のみ）。
    """
    base = _base_date(today)
    try:
        entry = formats.RENDERERS.resolve(fmt)
    except ValueError as exc:
        _fail(str(exc))
    writer, suffix = entry.factory, entry.suffix
    # `--against`（重ね描き）は現状の上に重ねるので過去の断面を出す `--at` とは同時に使えない。また重ねられるのは
    # HTML だけ＝他形式に渡したら黙って層を落とさず明示的に断る（fail-closed）。
    baseline_map: dict[str, tuple[date | None, date | None]] | None = None
    if against is not None:
        if at is not None:
            _fail("--against と --at は同時に使えない（--against は現状に重ね、--at は過去そのものを出す）")
        if fmt != "html":
            _fail(f"--against（ベースラインの重ね描き）は HTML のみ。--format {fmt} には重ねられない")
        try:
            baseline_map = dict(baseline.baseline_map(root, against, today=base))
        except baseline.BaselineError as exc:
            _fail(str(exc))
    if at is None:
        _export_from(
            root,
            root,
            out=out,
            today=base,
            draft=draft,
            commit=None,
            suffix=suffix,
            writer=writer,
            baseline_map=baseline_map,
        )
        return
    try:
        with baseline.tree_at(root, at) as snapshot:
            _export_from(
                root,
                snapshot,
                out=out,
                today=base,
                draft=False,
                commit=stamp.label_for(root, at),
                suffix=suffix,
                writer=writer,
            )
    except baseline.BaselineError as exc:
        _fail(str(exc))


DEFAULT_REPORT = "artifacts/wbs/REPORT"


@wbs_app.command("report")
def _report(
    against: Annotated[
        str | None, typer.Option(help="合意した時点（git のタグ・コミット）。渡すと前回からの変化を出す")
    ] = None,
    out: Annotated[Path | None, typer.Option(help=f"出力先（既定 {DEFAULT_REPORT}.html）")] = None,
    today: Annotated[str | None, typer.Option(help="基準日（YYYY-MM-DD。既定は実行日）")] = None,
    horizon_days: Annotated[int, typer.Option(help="「今後 N 日の予定」に入れる日数")] = 14,
    draft: Annotated[bool, typer.Option("--draft", help="未コミットの変更を含んだまま下書きとして出す")] = False,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """定例・最終報告の 1 枚（自己完結 HTML）を出す。

    マイルストーンの状況（達成／遅れ／予定）・遅れている作業・今後 N 日の予定を 1 枚にまとめる。
    `--against` に合意した時点（タグ・コミット）を渡すと、そこからの計画の変化も先頭に出す。
    出力を拒否する条件は `export` と同じ（検査失敗・日程 0 件・未コミット。`--draft` で下書きとして出せる）。
    """
    from harness import pm
    from harness.deliver import report as report_mod

    base = _base_date(today)
    changes = None
    if against is not None:
        try:
            changes = baseline.changes_since(root, against, today=base)
        except baseline.BaselineError as exc:
            _fail(str(exc))
    built, provenance, dirty = _prepare(root, root, today=base, draft=draft, commit=None)
    html = report_mod.render_report(
        built,
        today=base,
        provenance=provenance,
        draft=dirty,
        against=against,
        changes=changes,
        horizon_days=horizon_days,
        trace=pm.requirement_trace(root),  # 要件トレース被覆（要件層が無ければ節ごと出ない）
    )
    target = out if out is not None else root / (DEFAULT_REPORT + ".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    typer.echo(f"{target}: 報告を出力した　{provenance}")


@wbs_app.command("formats")
def _formats() -> None:
    """出せる形式の一覧（入れていない依存の形式はここに出ない＝選べる形式が使える形式）。"""
    render_catalog(formats.RENDERERS)


def _prepare(
    root: Path,
    source: Path,
    *,
    today: date,
    draft: bool,
    commit: str | None,
) -> tuple[wbs_mod.Wbs, str, bool]:
    """出力の**唯一の関門**：組み立て→検査→日程 0 件→未コミット を順に確かめ、(WBS, 由来の刻印, 下書きか) を返す。

    export も report もここを通る（拒否の順序と文言の第 2 実装を作らない）。どれか 1 つでも塞げば `_fail` が送出し、
    呼び出し側には到達しない（fail-closed）。`commit` を渡す＝過去の時点を出すので未コミット検査は掛けない。
    """
    # 例外の種類ごとに節を分ける（ruff format が `except (A, B):` を壊す既知の不具合を踏まないため）。
    try:
        built = wbs_mod.build(source, today=today)
    except ValueError as exc:  # 上書きの検証エラー（pydantic の ValidationError を含む）
        _fail(f"WBS を組み立てられない: {exc}")
    except OSError as exc:  # ファイルが読めない
        _fail(f"WBS を組み立てられない: {exc}")
    errors = [p for p in wbs_lint.check(source, today=today) if p.level == "error"]
    if errors:
        for problem in errors:
            typer.echo(f"error: {problem.message}", err=True)
        _fail(f"WBS の検査に {len(errors)} 件失敗した（直してから出す）")
    if built.span is None:
        _fail(
            "日程（start / due）を持つ作業単位が 1 件も無い。空のガントは出さない"
            "（work/ の単位に start・due を書くか、docs/wbs.yaml に手動行を足す）"
        )
    dirty = commit is None and stamp.is_dirty(root)
    if dirty and not draft:
        _fail(
            "作業ツリーに未コミットの変更がある。このまま出すと生成物に刻むコミットが実際の中身と食い違う"
            "（先にコミットする。下書きとして出すなら --draft を付ける）"
        )
    provenance = stamp.stamp(root, built, generated_at=datetime.now(UTC).astimezone(), commit=commit)
    return built, provenance, dirty


def _export_from(
    root: Path,
    source: Path,
    *,
    out: Path | None,
    today: date,
    draft: bool,
    commit: str | None,
    suffix: str,
    writer: Callable[..., None],
    baseline_map: dict[str, tuple[date | None, date | None]] | None = None,
) -> None:
    """`source` の中身から WBS を出す（`root` は出力先と git を見る先）。過去の時点も同じ道を通る。"""
    built, provenance, dirty = _prepare(root, source, today=today, draft=draft, commit=commit)
    target = out if out is not None else root / (DEFAULT_OUT + suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    if baseline_map is not None:
        writer(built, target, provenance=provenance, draft=dirty, baseline=baseline_map)
    else:
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
    base = _base_date(today)
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
    base = _base_date(today)
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
    base = _base_date(today)
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
