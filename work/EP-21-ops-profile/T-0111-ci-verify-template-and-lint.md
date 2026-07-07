---
id: T-0111
kind: task
status: done
title: CI verify テンプレ＝templates/ci の verify.yml＋ci_lint 本実装（実行しない構造検査）
created: 2026-07-07
depends_on: [T-0110]
verified_by: [tests/test_ci_lint.py::test_missing_verify_step_flagged]
---
# T-0111 CI verify テンプレ＋ci_lint 本実装

## 狙い
利用者（テンプレ複製先）のリポジトリが **PR→`uv run verify` のゲート**を最初から持てる雛形
`templates/ci/.github/workflows/verify.yml` を置き、T-0110 で器だけ作った `ci_lint` を本実装して
テンプレの**参照整合を verify で腐らせない**（deploy_lint が templates/serve を守るのと同型。
実行しない・GitHub Actions を動かさない・ネットワーク 0）。※自リポの CI は既にあるので触らない。

## 受け入れ基準
- **`templates/ci/.github/workflows/verify.yml`**（新規）：PR/push トリガ→checkout→uv セットアップ→
  `uv sync --all-extras`（AGENTS「開発・verify 環境は全部入り」）→`uv run verify` の 1 ジョブ。
  Python 版はリポの正（3.14）と一致させる。コメントで「複製先が編集する箇所」を明示。
- **`ops/ci_lint.py` 本実装**（実行しない・yaml で読むだけ・deploy_lint 同型）：
  - `templates/ci/` が在るとき、必須ファイル（`.github/workflows/verify.yml`）の欠落を error。
  - verify.yml に `uv run verify` を含む step が無ければ error（ゲートの本体が抜けた雛形を止める）。
  - `python-version`（または uv の指定）がリポの正（pyproject の requires-python）と食い違えば error。
  - `uv sync` step の extras 指定が `--all-extras` でなければ error（verify 環境の規約）。
  - `templates/ci/` が無いプロジェクトでは []（T-0110 の規約を維持）。
- **導線（DEC-0009/DEC-0016）**：`docs/ops.md` の CI 節に「テンプレの複製手順・ci_lint が何を守るか」を記載。
  `templates/serve/README.md` は触らない（CI は serve と独立の導線）。doclint が `templates/` 参照の実在を
  見るので、docs からの参照パスは実在するファイルに合わせる。
- 新 CLI コマンドは足さない（ci_lint は pm_checks 経由＝coverage_lint の対象外を維持）。
- core・ds・serve のロジック本体は変更しない。

## 触ってよいファイル
`templates/ci/**`（新規）・`src/harness/ops/ci_lint.py`・`docs/ops.md`（追記）・
`tests/test_ci_lint.py`（拡張）。serve/ds/core は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_ci_lint.py::test_missing_verify_step_flagged`（**unit**）：一時プロジェクトに verify step を
  **意図的に抜いた** verify.yml を置く→error が 1 件出る（欠落は構成から導く＝金メッキ禁止）。
- `test_ci_lint.py::test_repo_template_passes`（**integration**）：自リポの `templates/ci/` に対して
  `run_checks` が []（置いたテンプレ自身が規約を満たす＝E-0001 を e2e で腐らせない思想の CI 版）。
- `test_ci_lint.py::test_python_version_mismatch_flagged`（**unit**）：一時プロジェクトで版を食い違わせると error。
- `test_ci_lint.py::test_missing_all_extras_flagged`（**unit**）：`uv sync` の extras 指定を欠くと error。
- `uv run verify` 全体緑（ci_lint が pm 検査として実際に走ること＝T-0110 の結線の実証）。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：verify.yml を故意に壊す変異＝step 削除・版ずらしで lint が本当に落ちるか実測／
ネットワーク・実行を一切していないか／docs/ops.md からテンプレへの参照が doclint で実在検査されているか）
