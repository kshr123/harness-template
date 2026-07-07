---
id: T-0097
kind: task
status: done
title: time-based loop の導線（monitor 定期実行の runbook＋schedule 雛形・実行基盤は利用者環境）
created: 2026-07-07
depends_on: [T-0095, T-0093]
verified_by:
  - tests/test_agent_schedule_lint.py::test_real_repo_schedule_template_passes_clean
  - tests/test_agent_schedule_lint.py::test_missing_workflow_dispatch_is_error
  - tests/test_agent_schedule_lint.py::test_missing_stop_marker_is_error
  - tests/test_agent_schedule_lint.py::test_stop_marker_without_reference_is_error
  - tests/test_agent_schedule_lint.py::test_readme_without_stop_section_is_error
  - tests/test_agent_schedule_lint.py::test_unknown_script_is_error
  - tests/test_agent_schedule_lint.py::test_schedule_template_commands_resolve
  - tests/test_agent_schedule_lint.py::test_agent_profile_includes_schedule_lint
---
# T-0097 time-based loop の導線（done）

## 狙い
blog の time-based（時間間隔で起動・cancel/無効化で停止）を、**実行基盤を作らずに**運用へ落とす：
読む側（`agent monitor`・`data monitor`）は完成済みなので、**起動（trigger）を時間に接続する雛形と runbook**
だけを足す。実行基盤（cron・CI schedule・Claude 側 /loop・/schedule スキル）は利用者環境に委ねる
（EP-21 の CI テンプレと同じ「テンプレ＋構造 lint＋導線」の思想・DEC-0006/0008 の再発明回避）。

## 設計（fable 詳細設計・確定）
概念の核＝blog の停止条件の規律「止め方の無い routine を作らない」を、雛形への stop 宣言の埋め込み＋構造 lint で機械化する。実行基盤は作らない（DEC-0006/0008・パターンは deploy_lint を写す。EP-21 の ci_lint は main 未着地＝依存しない）。
- **置き場所 `templates/schedule/`（トップレベル）**：叩く先は `agent monitor`／`data monitor` 双方＝agent 専有にしない。**自リポの `.github/workflows/` には置かない**（置くと実 schedule が動く＝verify は時間起動を含まない、の違反）。
- **雛形 2 ファイル**：`monitor.yml`（`on: schedule.cron` ＋ `workflow_dispatch: {}` ＋ `permissions:`（contents:read/issues:write）＋ `concurrency:`（多重起動抑止）＋ 冒頭に停止手順コメント ＋ `uv run agent monitor --file-issue`）と `README.md`（コピー手順＋`## 停止（stop）` 節必須）。
- **`src/harness/agent/schedule_lint.py`（独立モジュール・deploy_lint 同型）**：`run_checks(root)->list[pm.Problem]`・`templates/schedule` が無ければ `[]`（コピー先で誤検知しない）・stdlib＋pyyaml（yaml/tomllib は関数内遅延＝DEC-0013）。**落とし穴**：pyyaml は YAML 1.1 で `on:` を bool `True` に読む＝トリガ取得は `doc.get("on", doc.get(True))` で両対応。
- **検査項目**：(a) 必須ファイル存在・(b) YAML 読める・(c) `schedule.cron` が 1 つ以上（time-based trigger）・**(d) `workflow_dispatch` 存在**・**(e) `monitor.yml` に「停止」コメント行があり README/docs を参照**・**(f) README に停止見出し**（d/e/f が本タスク固有の新検査＝stop 宣言の 3 点 AND・すべて error）・(g) cron が 5 フィールド・(h) `uv run <script>` が `pyproject.toml` `[project.scripts]` に実在（腐り検知の静的側・tomllib）・(i) `permissions:` 存在・(j) `concurrency:` は info。
- **CLI 腐り検知の分業**：lint は h（pyproject scripts の静的照合）まで。サブコマンド実在は pytest `test_schedule_template_commands_resolve`（typer app の registered_commands 照合）に置く＝lint に typer import を持ち込まず DEC-0013 を守る（`agent monitor` 改名で verify RED）。
- **profile 結線**：`agent/profile.py` を `pm_checks=(lint.run_checks, schedule_lint.run_checks)` に。profile は軽 import を維持（yaml/tomllib 遅延）。
- **導線**：docs/agent.md に time-based 節（使い方・**停止（disable/削除/`gh workflow disable`/Claude スキル解除）**・「止め方の無い routine を作らない」の明記・loops 表の time-based 行を実名に更新）＋ SKILL.md 1〜2 行。**新 CLI は足さない**（既存 `agent monitor` を時間に繋ぐだけ＝DEC-0016 の対象を増やさない）。

## 受け入れ基準（detailed）
- `templates/schedule/{monitor.yml,README.md}` が上記骨子で存在（自リポ雛形は schedule_lint 指摘 0 件）。
- `src/harness/agent/schedule_lint.py` が (a)〜(j) を検査。`PROFILE.pm_checks` に結線。
- docs/agent.md の time-based 節＋loops 表更新＋SKILL.md 導線が同タスクで入る。
- `uv run verify` 全成功（実 schedule 実行なし・無ネットワーク）。

## verified_by（代表テスト）
（T-0135 で停止宣言の検出を言語非依存の `# stop:` マーカーへ進化させた際、`test_missing_stop_comment_is_error`／
`test_stop_comment_without_reference_is_error` は `test_missing_stop_marker_is_error`／
`test_stop_marker_without_reference_is_error` へ改名・書き換え＝意味論は不変・下の一覧は現行名。）
- `tests/test_agent_schedule_lint.py::test_real_repo_schedule_template_passes_clean`
- `tests/test_agent_schedule_lint.py::test_missing_workflow_dispatch_is_error`
- `tests/test_agent_schedule_lint.py::test_missing_stop_marker_is_error`
- `tests/test_agent_schedule_lint.py::test_stop_marker_without_reference_is_error`
- `tests/test_agent_schedule_lint.py::test_readme_without_stop_section_is_error`
- `tests/test_agent_schedule_lint.py::test_unknown_script_is_error`
- `tests/test_agent_schedule_lint.py::test_schedule_template_commands_resolve`
- `tests/test_agent_schedule_lint.py::test_agent_profile_includes_schedule_lint`

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. schedule_lint から (d) workflow_dispatch 必須検査を外す → `test_missing_workflow_dispatch_is_error` が RED。
2. 出荷雛形から `workflow_dispatch:` を消す → `test_real_repo_schedule_template_passes_clean` が RED（宣言↔検査の双方向）。
3. `agent monitor` サブコマンドを改名 → `test_schedule_template_commands_resolve` が RED（腐り検知が生きている証明）。

## やらないこと
常駐デーモン・自前 cron・リポ内での実 schedule 実行（verify は時間起動を含まない＝無ネットワーク・決定性の維持）。
自リポの `.github/workflows/` に雛形を置かない。actionlint/act 等の実行系検査・cron の意味検証（範囲・曜日名）はしない
（5 フィールド数まで＝パーサ再発明の回避）。新 CLI コマンドは足さない。EP-21 の ci_lint に依存しない。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。効かせる guard を実際に壊して RED を実測（バックアップ→
ミューテート→対象テスト RED→バイト同一復元）。
- **M1**（(d) `workflow_dispatch` 必須検査を外す）→ `test_missing_workflow_dispatch_is_error` RED。✓
- **M-f**（(f) README 停止見出し検査を常に pass に）→ `test_readme_without_stop_section_is_error` RED。✓
- **M-h**（(h) script 実在検査を skip）→ `test_unknown_script_is_error` RED。✓
- **M4**（cli `monitor` サブコマンド改名）→ `test_schedule_template_commands_resolve` RED（腐り検知が生きている）。✓
- **M-e2（レビューで検出したギャップ→修正）**：初回実装では `_check_stop_comment` の後半＝「停止コメントが
  README/docs を参照していること」の副検査を外しても全テスト緑のまま通過した＝既存 `test_missing_stop_comment_is_error`
  は「停止」の語を消すため前半 `re.search` の早期 return ですり抜け、後半が赤経路で一度も実行されない tautology 欠落
  （T-0096 と同型・かつ本タスクの核＝「停止手順が runbook を指す」の機械化部分）。sonnet に差し戻し
  `test_stop_comment_without_reference_is_error`（「停止」の語は残し参照だけ外す）を追加。再ミューテートで確かに
  RED を Opus 側でも実測。✓
- `uv run verify` 全成功（実 schedule 実行なし・無ネットワーク）。**APPROVE**。
