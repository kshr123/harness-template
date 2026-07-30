"""実ブラウザ（headless Chrome）でページを開き、注入したスクリプトを走らせてから DOM を取り出す小さな土台。

文字列パースでは runtime 挙動（イベント発火後に class や textContent がどう変わるか）を確かめられない
＝逆写像や DOM 操作の変異が緑のまま通る。ここは実ブラウザで DOM を実際に組み、イベントを発火させてから
`--dump-dom` の HTML を返す。Chrome が無ければ skip する（理由と追跡先は skip メッセージに記す）。データ側・
JS 構文の検査は Chrome 無しでも常に回るので、fail-open にはならない。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# よくある実体の置き場（macOS の既定パス）と、PATH 上の実行名。
_APP_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
_PATH_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")


def chrome_path() -> str:
    """Chrome/Chromium の実体を探す。見つからなければ skip する（理由と追跡先は skip メッセージに記す）。"""
    for app in _APP_PATHS:
        if Path(app).is_file():
            return app
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    pytest.skip("ISS-0018: headless Chrome が無いので実測テストを飛ばす（Chrome を入れた環境では回る）")


def dump_dom(html: str, *, inject: str) -> str:
    """`html` に「load 後に `inject` を走らせる」スクリプトを差し込み、実ブラウザで開いて実行後の DOM を返す。

    `inject` は結果を DOM（属性・textContent など）に書き込む JS 断片にする＝呼び出し側はその DOM を読んで確かめる。
    """
    chrome = chrome_path()
    script = "<script>window.addEventListener('load',function(){" + inject + "});</script>"
    page = html.replace("</body>", script + "</body>", 1) if "</body>" in html else html + script
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "page.html"
        target.write_text(page, encoding="utf-8")
        proc = subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--dump-dom", target.as_uri()],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        # Chrome の実体は在る（chrome_path で確かめた）。ここで失敗するのは環境不在でなく実際の異常なので、
        # skip でなく失敗にする（skip にすると「Chrome が落ちても緑」という fail-open の窓ができる）。
        if proc.returncode != 0:
            raise AssertionError(f"headless Chrome が異常終了した（rc={proc.returncode}）: {proc.stderr[:500]}")
        return proc.stdout
