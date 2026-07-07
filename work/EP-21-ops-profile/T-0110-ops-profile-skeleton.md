---
id: T-0110
kind: task
status: todo
title: harness.ops 歩く骨組み（PROFILE 登録・空 ci_lint・config 1 行・docs/ops.md の器）
created: 2026-07-07
depends_on: [T-0085, T-0088]
verified_by: [tests/test_ops_profile.py::test_load_profiles_includes_ops]
---
# T-0110 harness.ops 歩く骨組み

## 狙い（端まで通る最小＝全体→詳細）
入力（`.harness/config.toml` の profiles）→処理（`harness.ops` を import）→出力（`PROFILE.pm_checks` に
`ci_lint.run_checks` が結線）→検証（verify の pm 検査に乗る）を **1 本通す**。以降のタスク（CI テンプレ・
リリース文書・shadow・CT・監視起票）はこの緑を保ったまま各部を差し替える。**EP-21 の思想＝実行しない・
構造 lint＋テンプレ＋プロファイル境界＋スキル導線で担保**（deploy_lint と同型）。実ランタイム基盤
（GitHub ランナー・k8s・クラウド）は作らない。

## 受け入れ基準（新規 `src/harness/ops/`・軽 import 規約＝DEC-0013）
- **`profile.py`**：`PROFILE = Profile(name="ops", pm_checks=(ci_lint.run_checks,))`。
  stdlib＋`harness.profiles`＋`harness.ops.ci_lint` のみ import（serve/profile.py と同型）。
- **`ci_lint.py`**：`run_checks(root: Path) -> list[pm.Problem]`。この骨組みでは
  **`templates/ci/` が無ければ []（誤検知しない）・在れば必須ファイル一覧（この時点では空タプル）を見るだけ**の器。
  docstring に「実行しない・構造検査のみ・deploy_lint 同型」の思想を明記（DEC-0009 の説明文規律）。
  依存は stdlib＋pyyaml のみ・yaml は関数内で遅延取り込み（deploy_lint と同じ規約）。
- **`__init__.py`**：`from harness.ops.profile import PROFILE` の再 export のみ。
- **配線**：`.harness/config.toml` の `profiles` に `"harness.ops"` を追加（1 行）。
- **導線（DEC-0009/DEC-0016）**：`docs/ops.md` を新規（serve.md 同型の正本の器＝EP-21 の対象範囲・
  「実行しない」思想・やらないこと（ランナー/k8s/クラウド/A/B/streaming は利用者環境）・以降のタスクで
  埋める節見出しだけ先に立てる）。`AGENTS.md` は変更しない（新 CLI を足さないので coverage_lint 対象外。
  ops は CLI を持たず pm_checks 経由で verify に乗る設計＝入口は docs/ops.md）。
- 新 CLI コマンド・新テンプレ実体はこのタスクでは**作らない**（次タスク T-0111 で templates/ci を足す）。
- core・ds・serve のロジック本体は変更しない。

## 触ってよいファイル
`src/harness/ops/**`（新規）・`.harness/config.toml`（profiles 1 行）・`docs/ops.md`（新規）・
`tests/{test_ops_profile.py,test_ci_lint.py}`（新規）・`tests/test_profiles.py`（既存拡張のみ）。
core（pm/checks/profiles）・ds・serve・agent のロジック本体は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_ops_profile.py::test_load_profiles_includes_ops`（**integration**）：`load_profiles(root)` の結果に
  `name == "ops"` の Profile が含まれ、pm_checks に `ci_lint.run_checks` が入る（test_profiles 同型）。
- `test_ops_profile.py::test_ops_profile_light_import`（**unit**）：`harness.ops.profile` を subprocess で
  import しても重い依存（fastapi・polars 等）が sys.modules に入らない（DEC-0013。serve の同種テスト同型）。
- `test_ci_lint.py::test_no_templates_ci_no_problems`（**unit**）：`templates/ci/` が無い一時プロジェクトで
  `run_checks` が []（コピー先の案件で誤検知しない）。
- 期待値はすべて構成（置いたファイル・置かないファイル）から導出。`uv run verify` 全体緑。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：profile の軽 import が本物か＝subprocess で実測／config を 1 行戻すと
検査が外れるか＝プロファイル境界の確認／ci_lint の器が「実行しない」を守っているか）
