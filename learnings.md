# learnings（気づき・使いにくかった点の記録）

1 件＝1 項目。冒頭に要点、続けて背景と対応。同じ失敗を繰り返さないために書く。
リポジトリや履歴が既に記録することは書かない。古くなったら消す。

---

## L-001 Windows のコンソール（cp932）は ✓ などの記号を出せず落ちる
- **要点**：出力に `✓✗` や日本語があると、Windows の既定の文字コード（cp932）で `UnicodeEncodeError` になり落ちる。
- **対応**：CLI の入口（`harness/cli.py`）で `sys.stdout/stderr.reconfigure(encoding="utf-8")` を最初に実行し、出力を UTF-8 に固定。「make に依存しない＝複数の OS で動く」前提の一部。
- **設計への反映**：不要（実装で解決）。「CLI は UTF-8 に固定する」は AGENTS.md の範囲で足りる。

## L-002 mypy strict ＋ 型情報の無い外部ライブラリ（python-frontmatter）は取り込みで失敗する
- **要点**：strict だと、型情報の無いライブラリの取り込みで失敗する。
- **対応**：`pyproject.toml` に `[[tool.mypy.overrides]] module=["frontmatter"] ignore_missing_imports=true` を追加。
- **設計への反映**：不要。新しい外部ライブラリを足したとき同じ設定が要ることがある、と覚えておく。

## L-003 日本語のコメント・メッセージは ruff の行の長さにすぐ当たる
- **要点**：日本語は文字が詰まるため、説明的な文が長くなりやすい。造語を使わず平易に書くと、なおさら長くなる。
- **対応**：行の長さを 120 に上げた（`pyproject.toml` の `[tool.ruff] line-length = 120`）。平易な日本語の説明を優先するための判断。
- **判断**：当初は 100（標準）にしていたが、平易な言葉を優先する方針で頻発したため 120 に変更した。

## L-004 STATUS.md は「タスクを変えたら uv run status」を挟まないとコミットで失敗する
- **要点**：STATUS.md は自動生成のファイルで、作り直した結果と一致するかをコミット前の検査と CI が確認する。タスクを変えた後に `uv run status` を忘れると失敗する。
- **対応**：コミット前の検査に `uv run status --check` を入れ、早い段階で気づけるようにした。AGENTS.md の手順にも書いた。
- **判断**：これは「二重に管理しない」ための正しい手間。自動で作り直してコミットに含める案もあるが、自動生成のファイルを勝手にコミットするのは分かりにくいので、今は「手で `uv run status`」を保つ。

## L-005 Windows で git が改行を CRLF に変換する警告を出す（複数 OS で差分の原因になる）
- **要点**：Windows の作業コピーで改行が CRLF になり、Linux の CI と差分になりうる。
- **対応**：`.gitattributes` に `* text=auto eol=lf` を置き、改行を LF に統一。
- **設計への反映**：不要（テンプレートの標準装備として `.gitattributes` を含める）。

## L-006 typer.Exit を console_script の入口で raise すると余計なエラー表示が出る
- **要点**：`[project.scripts]` の入口関数（typer.run を通さない）で `raise typer.Exit(1)` すると、捕捉されず余計なエラー表示（Traceback）が出る（終了コードは 1 で正しいが見苦しい）。
- **対応**：入口では `sys.exit(1)` を使う（task-lint）。typer.run を通すコマンド（status/check）は typer.Exit のままでよい。
- **設計への反映**：不要（実装の作法）。自分たちで使って試す中で見つかった＝仕組みが働いている例。
