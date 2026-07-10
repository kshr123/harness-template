---
id: T-0201
kind: task
status: done
title: coverage_lint の照合を uv run トークンの語境界つき正規表現に変える
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_coverage_lint.py::test_bare_mention_without_uv_run_is_not_reachable
  - tests/test_coverage_lint.py::test_negated_sentence_mention_is_not_reachable
  - tests/test_coverage_lint.py::test_substring_of_longer_word_does_not_falsely_match
  - tests/test_coverage_lint.py::test_uv_run_prefixed_bare_token_is_reachable
  - tests/test_coverage_lint.py::test_hyphenated_command_word_boundary
  - tests/test_coverage_lint.py::test_real_repo_all_cli_commands_are_reachable
---
# T-0201 coverage_lint の照合を語境界つき正規表現に変える

## 狙い
`src/harness/coverage_lint.py` の到達可能性判定は `token in corpus`（部分文字列一致）だった。この作法
だと、1 語のコマンド（`serve`・`status` 等）は本文にただ出現するだけで常に合格し（例：「配信（serve）
する」「進捗を確認する status」のような地の文でも合格）、否定文中の出現（「〜を直接叩かない」）も導線
に数えてしまう。モジュールの docstring 自身が「部分文字列一致」と自認しており、(b)（機械が検出する）
を名乗りながら実質は空振りしている。

## やったこと
- `coverage_lint._reachable(token, corpus)` を新設。判定を `token in corpus` から
  `re.compile(r"(?<![\w-])uv run " + re.escape(token) + r"(?![\w-])")` による正規表現探索に変更した。
  「`uv run` の直後に、前後を非単語文字（`\w` でも `-` でもない文字）で区切られた形でトークンが置かれて
  いる」ことだけを到達とみなす。対象集合の導出（`_command_tokens` の ast 解析・`_script_tokens` の
  `pyproject.toml` 走査）は変更していない。
- `run_checks` の 2 箇所（typer 走査・`[project.scripts]` 走査）の判定を `token in corpus` から
  `_reachable(token, corpus)` に置き換えた。
- モジュール docstring を新しい判定作法に合わせて更新した。
- 否定文の検出のような「意味を読む」機構は作っていない（機械には無理なので語境界の照合に留めた）。
  否定文の例（「data blocks を直接叩かない」）は、`uv run` の直後に置かれていない限り自然と到達扱いに
  ならない（`uv run` プレフィックス要求の副作用で解決される。専用の否定検出は無い）。

## 検査を厳しくした結果（赤くなったコマンドの有無）
現リポの全 CLI コマンド（typer 装飾子＋`[project.scripts]`）に対して新しい語境界つき照合を当てたところ、
免除済みの `changelog`（Phase 0 の未実装骨格。理由は既存の `_EXEMPT` のまま）を除き、**赤くなったコマンド
は 0 件**だった。既存のスキル/正本 docs（`.claude/skills/**`・`AGENTS.md`・`README.md`・`docs/*.md`）は
既にどのコマンドも `` `uv run <コマンド>` `` の実際に使える形で案内していたため、判定を厳しくしても
案内の追加は不要だった（`test_real_repo_all_cli_commands_are_reachable` の回帰テストで確認）。

## テスト（先に書いた。期待値はテストデータの構成から導く）
- `test_bare_mention_without_uv_run_is_not_reachable`：`serve` という語が地の文にただ出現するだけでは
  到達とみなさない。
- `test_negated_sentence_mention_is_not_reachable`：否定文中の出現（`uv run` の後ろではない）も到達に
  ならない。
- `test_substring_of_longer_word_does_not_falsely_match`：`servex`／`deserve` のような部分文字列に誤って
  ヒットしないこと、かつ本物の `` `uv run serve --help` `` は到達すること。
- `test_uv_run_prefixed_bare_token_is_reachable`：`` `uv run serve --help` `` の形は到達とみなす。
- `test_hyphenated_command_word_boundary`：ハイフンを含むコマンド（`task-lint` 相当）でも語境界が正しく
  効く（`foo-linter` に誤ってヒットしない／本物の `` `uv run foo-lint` `` は到達する）。
- 既存の `test_every_exempt_reason_is_nonempty`／`test_blank_exempt_reason_raises`／
  `test_blank_exempt_reason_for_script_raises` は無改修のまま緑（免除リストの理由必須の作法は保たれる）。
- `test_real_repo_all_cli_commands_are_reachable`（既存の回帰テスト）：現リポ全体で新しい照合でも赤が
  出ないことを確認する。
