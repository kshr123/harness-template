---
id: T-0073
kind: task
status: done
title: Windows CI ジョブ（OS matrix で ubuntu＋windows・OS 差を CI で止める）
created: 2026-07-06
depends_on: [T-0045]
verified_by:
  - tests/test_ci_config.py::test_ci_runs_verify_on_linux_and_windows
  - tests/test_ci_config.py::test_ci_uses_the_shared_verify_command
---
# T-0073 Windows CI ジョブ

## 背景
このリポは cli.py で cp932 コンソールを UTF-8 に再設定し、パスは pathlib で書く等クロスプラットフォームを前提にするが、
CI は ubuntu だけ＝Windows 差（コンソール符号化・パス区切り・改行）が検出できない。OS matrix で windows-latest を足す。

## 受け入れ基準
- `.github/workflows/ci.yaml` の verify ジョブを `strategy.matrix.os: [ubuntu-latest, windows-latest]` に（`fail-fast: false`）。
  両 OS でロック一致確認→`uv sync --all-extras`→`uv run verify` の同じ手順（完了の定義を OS 間で一致させる）。
- 退行を機械で止める meta-test（`tests/test_ci_config.py`）：matrix に両 OS が在る・共通コマンド `uv run verify`＋all-extras を使う。

## 触ってよいファイル
`.github/workflows/ci.yaml`＋`tests/test_ci_config.py`。

## 結果
実装（OS matrix＋meta-test）・verify 緑で done。宣言的 CI 設定のため独立エージェントレビューでなく meta-test（退行の番人）で
担保（T-0066 と同型）。Windows 実行の実結果は CI 側で確認する（ローカルでは Windows を回せない）。ideal-build-plan Wave 4。
