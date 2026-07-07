---
id: T-0101
kind: task
status: done
title: commit-msg の作業単位 ID 検査（pm の ID 一覧を再利用・来歴を機械で守る）
created: 2026-07-07
depends_on: [T-0100]
verified_by: [tests/test_commit_lint.py::test_message_without_id_fails, tests/test_commit_lint.py::test_message_with_existing_id_passes]
---
# T-0101 commit-msg の作業単位 ID 検査

## 狙い
全コミットが `EP-xx T-xxxx：…` を冒頭に書く強い慣習が**未検査**（人・エージェントの自制頼み）。
`commit-msg` フックで「メッセージが `work/` に実在する作業単位 ID を含むか」を機械検査し、
「何をどの根拠で変えたか」の来歴を一段強くする。ID の正本は **`pm.load_tree` の木だけ**＝新しい ID 一覧を
作らない（二重管理を作らない＝DEC-0009 の思想）。T-0100 で確立した型（執行点＋配線の常在検査）に従う。

## 受け入れ基準
- **`src/harness/commit_lint.py`（新規・小さく）**：`lint_message(root: Path, message: str) -> list[pm.Problem]`。
  - 検査：メッセージ 1 行目に、`pm.load_tree(root)` から得た**実在 ID**（EP-… / T-… / E-…）が 1 つ以上含まれること。
    ID らしき文字列（例 `T-9999`）があっても実在しなければ error（打ち間違い・架空 ID を止める）。
  - 免除（理由をコード内コメントに明記）：`Merge` / `Revert` / `fixup!` / `squash!` で始まるメッセージ、および
    空メッセージ（git 側が別途拒否）。免除は接頭辞の明示リストだけ＝fail closed（coverage_lint の `_EXEMPT` と同型）。
  - import は stdlib＋`harness.pm` のみ（core の検査・プロファイル非依存）。
- **入口**：`pyproject.toml` の `[project.scripts]` に 1 本（例 `commit-msg-lint = "harness.cli:commit_msg_lint_main"`。
  引数＝git が渡すメッセージファイルのパス）。typer の `@command` を増やす場合は coverage_lint が導線を要求するため、
  **同じタスクで正本 docs に使い方を書く**（下記導線）。
- **`.pre-commit-config.yaml`**：`stages: [commit-msg]` の local フックを追加（`entry: uv run commit-msg-lint`）。
  既存フックは変更しない。
- **導線（DEC-0009/DEC-0016）**：`AGENTS.md` のコマンド節（または pre-commit の使い方を書いている正本 docs）に
  2 行以内で追記：(1) `commit-msg-lint` が何を検査するか、(2) 有効化には `pre-commit install --hook-type commit-msg`
  が必要なこと（既定の `pre-commit install` では commit-msg ステージは入らない）。coverage_lint が緑であること。
- `uv run verify` 全体緑（新テスト含む）。

## 触ってよいファイル
`src/harness/commit_lint.py`（新規）・`src/harness/cli.py`（main 関数 1 本の追加のみ・既存コマンドの振る舞い不変）・
`pyproject.toml`（scripts 1 行）・`.pre-commit-config.yaml`（commit-msg フック追加）・
`tests/test_commit_lint.py`（新規）・`AGENTS.md` または正本 docs（2 行以内）。
`pm.py` 本体は変更しない（読むだけ）。

## 検査（テスト先書き・構成から導く・マーカー必須）
一時ディレクトリに小さな `work/` 木（EP 1 つ＋T 2 つ等）を**テスト内で構成**し、期待値はその構成から導出する
（`test_agent_lint.py` と同型・実装出力のコピー禁止）。
- `test_commit_lint.py::test_message_with_existing_id_passes`（**unit**）：構成した木に実在する ID を含む
  メッセージ → 問題 0 件。
- `test_commit_lint.py::test_message_without_id_fails`（**unit**）：ID を含まないメッセージ → error 1 件
  （メッセージに「実在 ID を含めよ」の趣旨と ID の例が入る）。
- `test_commit_lint.py::test_unknown_id_fails`（**unit**）：木に無い `T-9999` を含むメッセージ → error
  （架空 ID を通さない）。
- `test_commit_lint.py::test_exempt_prefixes_pass`（**unit**）：`Merge …`／`Revert …`／`fixup! …` → 問題 0 件。
- CLI 入口（メッセージファイルのパスを受けて exit code を返す）は CliRunner または subprocess で 1 本
  （**integration**）。マーカー未登録は `--strict-markers` で失敗するため登録済みのものだけ使う。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：ID の正本が pm.load_tree の一本だけか＝二重管理が生まれていないか／
免除接頭辞が広すぎないか（何でも通る抜け道になっていないか）／実測＝実リポで `git commit` して
拒否・通過の両方を確認したか／commit-msg ステージ未 install の環境で黙って素通りになる点が docs に明記されているか）
