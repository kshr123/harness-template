---
id: T-0068
kind: task
status: done
title: doclint＝正本ドキュメントが参照する DEC/ISS/パス/コマンドの実在検査を PM_CHECKS へ
created: 2026-07-06
depends_on: [T-0046]
verified_by:
  - tests/test_doclint.py::test_reference_to_prefix_whose_home_dir_is_absent_is_error
  - tests/test_doclint.py::test_missing_iss_reference_is_error
  - tests/test_doclint.py::test_iss_check_skipped_on_github_backend
  - tests/test_doclint.py::test_missing_path_is_error
  - tests/test_doclint.py::test_globs_placeholders_and_bare_words_are_not_flagged
  - tests/test_doclint.py::test_known_command_is_ok_and_unknown_is_info
  - tests/test_doclint.py::test_skills_are_scanned
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0068 doclint（正本ドリフトの機械検査）

## 背景
AGENTS.md・スキル・docs/method.md・docs/learnings.md は「DEC-XXXX を参照」「`uv run verify`」「`docs/...` を見る」等の
リンクを大量に持つが、対象が消える/改名されると**黙って死にリンク**になる（ISS-0003）。参照の実在を機械で止める。

## 受け入れ基準
- `src/harness/doclint.py`（core・stdlib のみ）に `run_checks(root) -> list[pm.Problem]`：
  - 対象：`AGENTS.md`・`CLAUDE.md`・`docs/method.md`・`docs/learnings.md`・`.claude/skills/**/*.md`・`docs/decisions/*.md`（本文）。
  - 検査（見つかった参照が実在するか。**error/warn の別は妥当な粒度で**）：
    - `DEC-\d+` → `docs/decisions/DEC-XXXX-*.md` が在る。`ISS-\d+` → `issues/ISS-XXXX-*.md` が在る（github backend のときは skip）。
    - 本文中の相対パス（`docs/...`・`src/...`・`work/...` 等・コード塊やコマンド例の明確なパス）→ 実在する。
      誤検出を避けるため**判定は保守的に**（明らかにパスの形のものだけ・glob/変数を含むものは除外）。
    - `uv run <サブコマンド>`（verify/status/task-lint/data …）→ 実在するコマンド（既知リスト or CLI から導出）。
  - 各 Problem はどのファイル・どの参照かを含む。
- `checks.py` の PM_CHECKS に doclint を追加（`uv run verify` の PM 検査で走る）。core の検査（プロファイル非依存）。

## 触ってよいファイル
新規 `src/harness/doclint.py`＋`src/harness/checks.py`（PM_CHECKS に 1 行）＋`tests/test_doclint.py`。
`pm.py` は Problem 型を import するだけ（編集しない）。既存 docs は**直さない**（死にリンクが見つかってもこのタスクでは検査の追加のみ・
既存が全部通ることは確認する。落ちるなら誤検出か本物かを切り分けて報告）。

## 検査（テスト先書き・構成から導く）
- 一時プロジェクトに「存在する DEC を参照する doc」→ 問題なし・「存在しない DEC-9999 を参照する doc」→ error（構成から）。
- 存在しないパス `src/nope.py` を参照 → error。存在するパス → 問題なし。glob/変数入りは誤検出しない。
- 未知コマンド `uv run nope` → error（or warn）。既知コマンド → 問題なし。github issues backend では ISS 参照検査を skip。
- **現リポの実 docs で doclint が 0 error**（既存の正本が全部実在参照＝回帰の番人）。落ちたら本物の死にリンクなので報告。

## 独立レビュー（2026-07-06・maker≠checker）
「現リポ error 0（誤検出なし）」と「本物の死にリンク（DEC/ISS/パス/コマンド）は全種検出」の両立を実測で確認
（対象26ファイル・抽出内訳・URL/句読点/前方一致のエッジ・github skip・4.1ms/回）。minor 反映：プレースホルダ正規表現を
大文字小文字無視に（docs の小文字 `DEC-xxxx` の latent 誤検出を除去）・未知コマンドの level を `warn`→`info`（pm.Problem の
"error"|"info" 規約に沿う）・コードフェンス内も走査する割り切りを docstring に明記。

## 結果
実装・独立レビュー（反映）・verify 緑で done。ISS-0003 消化＝promoted_to。ideal-build-plan Wave 4。
