"""配信プロファイルの CLI 入口（typer）。`uv run serve` で champion を FastAPI 配信する。

中核・ds の CLI とはモジュールを分ける（プロファイル境界）。fastapi/uvicorn（extra serve）が
無い環境では導入方法を案内して exit 1 する（生の ImportError の栈を吐かない）。重い import（uvicorn・
fastapi 経由の app）はコマンドの中で遅延取り込みする（--help を軽く保つ・未導入の案内を出せる）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

# Windows コンソール（cp932）でも日本語・記号を出せるよう UTF-8 に固定（ds/cli.py と同じ作法）。
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

serve_app = typer.Typer(help="champion を FastAPI で配信する（配信プロファイル・extra serve）", add_completion=False)


@serve_app.command("serve")
def _serve(
    work: Annotated[str, typer.Option(help="モデルの作業単位ID（保存時の work）")],
    name: Annotated[str, typer.Option(help="モデル名（保存時の name）")],
    version: Annotated[str | None, typer.Option(help="モデルの版（省略時は現 champion）")] = None,
    host: Annotated[str, typer.Option(help="待ち受けホスト")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="待ち受けポート")] = 8000,
    log_dir: Annotated[
        Path | None, typer.Option(help="予測 JSONL の置き場（既定 artifacts/serve/predictions/<モデル名>）")
    ] = None,
    root: Annotated[Path, typer.Option(help="プロジェクトの根")] = Path("."),
) -> None:
    """champion（または指定版）を読み込み、FastAPI アプリを uvicorn で起動する。

    起動時にモデルを読み込む＝champion が無い・保存が壊れている場合はここで止まる（黙って空で立たない）。
    """
    try:
        import uvicorn

        from harness.serve.app import create_app
    except ImportError as exc:
        typer.echo(f"fastapi/uvicorn が無い（配信 extra 未導入）。`uv sync --extra serve` で導入する: {exc}")
        raise typer.Exit(1) from exc
    app = create_app(root, work=work, name=name, version=version, log_dir=log_dir)
    uvicorn.run(app, host=host, port=port)


def serve_main() -> None:
    """`uv run serve` の入口。"""

    serve_app()
