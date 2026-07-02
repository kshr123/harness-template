# learnings（教訓・friction の蓄積）

1 教訓＝1 項目。冒頭に要点、続けて背景と対応。同じ失敗を繰り返さないために書く。
既にリポや履歴が記録することは書かない。古くなったら消す。

---

## L-001 Windows コンソール（cp932）は ✓ など非 ASCII 記号を出せず crash する
- **要点**：CLI 出力に `✓✗✅` や日本語があると、Windows 既定の cp932 で `UnicodeEncodeError`。
- **対応**：CLI 入口（`harness/cli.py`）で `sys.stdout/stderr.reconfigure(encoding="utf-8")` を最初に実行。make 非依存と同じ「クロスプラットフォーム前提」の一部。
- **PM設計への反映**：不要（実装レベルで解決）。ただし「CLI は UTF-8 を強制する」を規約として残す価値あり→ AGENTS.md の範囲で足りる。

## L-002 mypy strict ＋ 型スタブの無い外部ライブラリ（python-frontmatter）は import で赤になる
- **要点**：strict だと未型付けライブラリの import が `import-untyped` 等で赤。
- **対応**：`pyproject.toml` の `[[tool.mypy.overrides]] module=["frontmatter"] ignore_missing_imports=true`。
- **PM設計への反映**：不要。ただし「新しい外部依存を足したら override が要ることがある」を verify スキルの注記に将来足すか検討（今は見送り）。

## L-003 日本語コメント・メッセージは ruff の行長（100）にすぐ当たる
- **要点**：CJK は文字数が詰まるため、説明的な日本語メッセージが 100 桁超になりやすい。
- **対応**：メッセージを短く保つ。現時点で line-length 変更はしない（適正規模＝標準に合わせる）。
- **判断**：友好度と規約のトレードオフ。今は「短く書く」で対応。多発するなら line-length=120 を検討（保留）。

## L-006 typer.Exit を console_script 直入口で raise すると Traceback が漏れる
- **要点**：`[project.scripts]` の入口関数（typer.run を通さない）で `raise typer.Exit(1)` すると、未捕捉で Traceback が表示される（終了コードは 1 で正しいが見苦しい）。
- **対応**：直入口では `sys.exit(1)` を使う（task-lint）。typer.run を通すコマンド（status/check）は typer.Exit のままでよい。
- **PM設計への反映**：不要（実装の作法）。ドッグフーディングで発見＝仕組みが機能している例。

## L-005 Windows で git が LF→CRLF 変換の警告を出す（クロスプラットフォームのテンプレで差分の温床）
- **要点**：Windows の作業コピーで改行が CRLF になり、Linux CI と差分になりうる。
- **対応**：`.gitattributes` に `* text=auto eol=lf` を置き、`git add --renormalize .` で LF に統一。
- **PM設計への反映**：不要（テンプレの標準装備として `.gitattributes` を含める）。

## L-004 STATUS.md は「タスク変更→uv run status」を挟まないとコミットで赤になる
- **要点**：STATUS は生成物で再生成一致を CI/フックが検査するため、タスク編集後に `uv run status` を忘れると赤。
- **対応**：pre-commit フックに `uv run status --check` を入れて早い層で気づけるようにした。AGENTS.md の手順にも明記。
- **PM設計への反映（やりやすさ）**：これは「二重管理をしない」ための正しい摩擦。将来 status を pre-commit で自動再生成（--check でなく生成）する案もあるが、生成物を自動コミットするのは分かりにくいので今は「手で `uv run status`」を維持。→ 運営設計書 §4.6 の方針と一致。変更不要。
