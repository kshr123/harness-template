---
id: T-0164
kind: task
status: done
title: subprocess の text=True に encoding を必須化し、verify を緑に戻す
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_conventions.py::test_real_repo_has_no_subprocess_without_encoding
  - tests/test_commit_lint.py::test_cli_entry_exit_codes
---
# T-0164 subprocess の encoding 未指定を機械検査で止め、verify を緑に戻す

## 背景
`uv run pytest tests/test_commit_lint.py::test_cli_entry_exit_codes` が Windows で失敗する。
`subprocess.run(..., text=True)` は `encoding=` を省くとロケールの符号化方式（この環境では cp932）で
子プロセスの出力を復号する。ハーネスの CLI は日本語のメッセージを UTF-8 で出すため、読み取りスレッドが
`UnicodeDecodeError` で落ち、`proc.stdout` が `None` になる。

同じ形の呼び出しが 10 か所ある。うち 2 か所（`ds/models.py`・`agent/store.py` の git 由来情報の取得）は
本番コードで、しかも例外の捕捉が `OSError, subprocess.SubprocessError` なので `UnicodeDecodeError` を
取りこぼしてクラッシュする。

## 受け入れ基準
- `conventions` lint が「`subprocess` の呼び出しで `text=True`／`universal_newlines=True` を使うのに
  `encoding=` が無い」を error にする（先に検査を書き、既存の 10 か所が失敗することを確認する）。
- 10 か所すべてに `encoding="utf-8"` を付ける。git 由来情報の取得は `UnicodeDecodeError` も捕捉する。
- `uv run verify` がすべて成功する。

## 検査の期待値の導出
検査のテストは一時ディレクトリに書いたコードの構成から期待値を導く（`text=True` かつ `encoding` 無し＝
error が 1 件・`encoding` 付き＝0 件・`text=False`＝0 件）。実装の出力は写さない。
