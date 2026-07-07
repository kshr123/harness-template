---
id: T-0104
kind: task
status: done
title: coverage_lint が [project.scripts] の plain main も導線検査する（ISS-0014＝DEC-0016 の死角を塞ぐ）
created: 2026-07-07
depends_on: [T-0088]
verified_by: [tests/test_coverage_lint.py::test_orphan_project_script_is_error_until_linked, tests/test_coverage_lint.py::test_real_repo_all_cli_commands_are_reachable]
---
# T-0104 coverage_lint に [project.scripts] 走査を足す（ISS-0014）

## 狙い（ISS-0014 の解消）
coverage_lint（T-0088・EP-19）の AST 走査は typer の `@<app>.command("name")` 装飾子だけを拾い、
`[project.scripts]` に登録した plain main（`typer.run` 型。verify/status/changelog/`commit-msg-lint` 等）を
**導線検査の対象にしない**。結果、エージェントが `[project.scripts]` 経由でコマンドを足すと、スキル/正本
docs への導線を張り忘れても verify が緑になる＝DEC-0016「新 CLI は導線必須」の機械検査に穴が残る。
この穴を塞ぐ（`commit-msg-lint` は実際には AGENTS.md に導線があるが、**無くても検査が素通りしていた**のが問題）。

## 受け入れ基準
- **`pyproject.toml` の `[project.scripts]` のキー（コマンド名）を走査対象に足す**。読み取りは
  **stdlib の `tomllib`** で行う（`import harness.*` を増やさない＝coverage_lint の「重い依存を引き込まない」
  方針を維持。ネットワーク・重い依存ゼロ）。ルートに `pyproject.toml` が無ければ静かに読み飛ばす（既存の
  「無いファイルは読み飛ばす」作法と揃える）。
- **到達可能性の判定は既存と同一**：トークン＝スクリプト名（例 `commit-msg-lint`・`task-lint`）が
  `_corpus`（`.claude/skills/**`＋AGENTS.md＋README.md＋docs/*.md）に部分文字列で 1 回以上現れること。
  現れず・`_EXEMPT` にも無ければ **error**（どのコマンドが未到達かを名指し。メッセージは pyproject.toml 由来と
  分かる語を含める）。
- **既存の typer 走査は挙動不変**（既存テスト 12 本はそのまま緑）。同一トークンを typer 走査と scripts 走査の
  両方が拾っても、**同じ token の error は 1 回だけ**にする（重複報告しない）。
- **免除は既存の `_EXEMPT`（理由必須・空は ValueError）をそのまま使う**。`changelog` は
  **未実装の Phase 0 骨格**（`cli.py` は「未実装」を echo するだけ）なので `_EXEMPT` に
  **理由つきで**足す。理由文に「実装時に導線を張り、この免除を外すこと」を明記する（silent 免除にしない）。
- **docstring を更新**：走査対象が typer 装飾子＋`[project.scripts]` の 2 経路であることを冒頭方針に書く。
- `uv run verify` 全成功（現リポの全 `[project.scripts]` コマンドが導線 or 免除で緑＝回帰の番人が守る）。

## テストの要点（数値・期待値は構成から導出。金メッキ禁止）
- **回帰の核**：一時プロジェクトに `pyproject.toml` を書き、`[project.scripts]` に導線の無いコマンド
  （例 `frob = "x:main"`）を 1 つ入れる → error に `frob` と pyproject 由来の語が出る。導線（skill か
  AGENTS）を 1 行足す → error が消える。**このケースが T-0088 時点では検出できなかった**ことが要点。
- **免除**：`[project.scripts]` のコマンドを `_EXEMPT` に理由つきで入れると error が消える／理由が空なら
  ValueError（既存 `test_blank_exempt_reason_raises` と同型）。
- **typer 挙動不変**：既存の orphan テスト群が緑のまま（typer 経路は 1 バイトも変えない）。
- **重複しない**：typer app と同名のスクリプト（例 `data`）が両経路で拾われても error は 1 回だけ。
- **現リポ回帰**：`test_real_repo_all_cli_commands_are_reachable` 相当が scripts 経路込みで緑
  （`changelog` は免除で緑・他は導線で緑）。

## 触ってよい範囲
`src/harness/coverage_lint.py`・`tests/test_coverage_lint.py`・この item.md のみ。`pyproject.toml` の
`[project.scripts]` 定義自体は変えない（`changelog` の登録も残す＝免除で扱う）。ISS-0014 の state 更新は別途。
