---
id: T-0069
kind: task
status: done
title: conventions lint（グローバル種検出・実験 --test 必須・skip/xfail の ISS 参照必須）を機械検査に
created: 2026-07-06
depends_on: [T-0068]
verified_by:
  - tests/test_conventions.py::test_np_random_seed_call_is_error_with_file_and_line
  - tests/test_conventions.py::test_default_rng_and_explicit_seed_args_are_ok
  - tests/test_conventions.py::test_work_script_without_test_flag_is_error
  - tests/test_conventions.py::test_short_flag_before_test_is_not_false_positive
  - tests/test_conventions.py::test_global_seed_in_code_subpackage_is_scanned
  - tests/test_conventions.py::test_imperative_skip_without_iss_is_error
  - tests/test_conventions.py::test_imperative_skip_with_iss_and_importorskip_are_ok
  - tests/test_conventions.py::test_from_import_seed_call_is_error
  - tests/test_conventions.py::test_skip_without_iss_reference_is_detected
  - tests/test_conventions.py::test_current_repo_has_no_convention_errors
---
# T-0069 conventions lint（ISS-0002）

## 背景
AGENTS のテスト規約のうち 3 つが「レビュー観点」止まりで verify が落ちない：グローバル種禁止・実験 `--test` 必須・
skip/xfail の ISS 参照必須。DEC-0005 の「退行を止める検査を先に書く」に沿って機械検査へ昇格する（ISS-0002）。

## 受け入れ基準
- **グローバル種検出＋実験 --test**（静的検査・`src/harness/conventions.py`・stdlib の ast のみ）：`run_checks(root) -> list[pm.Problem]`
  - `np.random.seed(`/`numpy.random.seed(`/`random.seed(` の呼び出しを `src/`・`tests/`・`work/**/code/*.py` から ast で検出 → error
    （明示引数 seed=/random_state= は対象外＝関数呼び名で判定）。どのファイル・行かを含む。
  - 実験スクリプト（`work/**/code/*.py` で argparse を使う train 系）に `--test` 引数が無ければ error（argparse の add_argument で
    "--test" を追加しているかを ast/文字列で保守的に判定・docstring に方針明記）。
  - PM_CHECKS に追加（`uv run verify` で走る・core 検査）。
- **skip/xfail の ISS 参照**（conftest の収集フック拡張）：`@pytest.mark.skip`/`skipif`/`xfail` が付いたテストは reason に
  `ISS-\d+` を含むこと。含まなければ collect でエラー（既存の marker 検査と同じ流儀・`harness/testing.py` にヘルパを足して conftest から呼ぶ）。
- **現リポで 0 違反**（既存はグローバル種なし・skip なし・train.py に --test あり＝回帰の番人）。落ちたら本物の違反として報告。

## 触ってよいファイル
新規 `src/harness/conventions.py`＋`src/harness/testing.py`（skip/xfail ヘルパ）＋`tests/conftest.py`（収集フック拡張）＋
`src/harness/checks.py`（PM_CHECKS に 1 行）＋新規 `tests/test_conventions.py`。pm.py は Problem を import するだけ。

## 検査（テスト先書き・構成から導く）
- グローバル種：tmp に `np.random.seed(0)` を含む .py → error・`np.random.default_rng(0)` のみ → 問題なし（明示は許容）。
- --test：tmp の experiment 風スクリプトに `--test` 追加あり → OK・無し → error。
- skip/xfail：ヘルパ関数に「reason に ISS-1234 を含む skip」→ OK・「理由に ISS 無し skip」→ 検出（実テストに実 skip を足さず**ヘルパの単体テスト**で・reason 文字列と marker 名を渡す形）。
- 現リポ：`conventions.run_checks(Path("."))` が 0 error（回帰の番人）。

## 独立レビュー（2026-07-06・maker≠checker）
中心形（np.random.seed 等）の確実な検出・現リポ 0 誤検出・既存 collect 無破壊を実測で確認。important 3 件を反映：
(I-1) `add_argument("-t","--test")` の偽陽性→位置引数のどれかが --test なら可、(I-2) 命令形 `pytest.skip/xfail` が
マーカー検査を素通り→静的検査で ISS 参照を要求（importorskip は optional 依存の入口で対象外）、(I-3) work の走査が
`code/*.py` 直下のみ→`code/**` 再帰に。minor（from-import した seed の直接呼び出し）も検出に追加。回帰テスト 5 本追加。

## 結果
実装・独立レビュー（3 importants＋from-import を反映）・verify 緑で done。ISS-0002 消化＝promoted_to。ideal-build-plan Wave 4。
