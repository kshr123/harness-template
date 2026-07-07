---
id: T-0115
kind: task
status: todo
title: data monitor --file-issue＝PSI_ALERT 超で issues に冪等起票（監視→課題の閉ループ・門番にしない）
created: 2026-07-07
depends_on: [T-0114]
verified_by: [tests/test_monitor_file_issue.py::test_file_issue_idempotent_and_exit_zero]
---
# T-0115 data monitor --file-issue（監視→課題起票の閉ループ）

## 狙い
`data monitor` に `--file-issue` オプションを足し、band が `PSI_ALERT`（0.25）超の列があるとき
issues backend に**冪等に**起票する。**既存 2 部品（`ds/monitor.py`・`issues.py`）の合成のみ**＝
新しい監視ロジック・新しい起票 backend は作らない。**門番にしない思想は維持**：exit code は常に 0・
起票は副作用（監視の数字は人が読む・CI を落とさない＝monitor.py 冒頭の規約）。これで EP-21 の輪
（配信→監視→課題→再学習の閉ループ）が閉じる。

## 受け入れ基準
- **`ds/cli.py` の `data monitor`** に `--file-issue`（フラグ・既定 off）を追加。既定 off の挙動は
  従来と完全に同一（出力・exit code とも不変＝後方互換）。
- **起票の中身**：alert band の列がある場合のみ 1 件起票。タイトル・本文は決定的（対象列・psi 値・
  基準/配信ログの指紋・日付）＝同じ入力なら同じ内容。`issues.py` の既存 API（next_id・backend 抽象）を
  使い、file backend でも GitHub backend でも同じ経路（backend 分岐を新設しない）。
- **冪等**：同じドリフト内容で 2 回実行しても課題は増えない（open な同種課題の有無で判定。判定キーは
  決定的な内容指紋＝実装で新しい仕組みを作らず既存 fingerprint 部品を使う）。
- **exit 0**：alert が出ても・起票しても・起票先が既に在っても exit code は 0（門番にしない）。
  起票の成否は標準出力に 1 行（起票した ID or 既存 ID を表示）。
- **導線（DEC-0009/DEC-0016・coverage_lint）**：既存 CLI の**オプション追加**なので新コマンドは増えないが、
  同じタスク内で `docs/ops.md` の監視閉ループ節＋`data monitor` の正本 docs（既存の monitor 記載箇所）に
  `--file-issue` の使い方を追記。retrain.yml（T-0114）の monitor step のコメントに `--file-issue` を反映
  （閉ループの結線を雛形にも示す）。
- core・serve は変更しない。`ds/monitor.py` のロジック（psi/band/PSI_ALERT）は変更しない（読むだけ）。

## 触ってよいファイル
`src/harness/ds/cli.py`（オプション追加）・必要なら `src/harness/ds/monitor.py` に**純関数の追加のみ**
（既存関数のシグネチャ・挙動は不変）・`docs/ops.md`（追記）・`data monitor` を記載している既存正本 docs
（追記）・`templates/ci/.github/workflows/retrain.yml`（コメント 1 行）・
`tests/test_monitor_file_issue.py`（新規）。issues.py・serve・core は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_monitor_file_issue.py::test_file_issue_idempotent_and_exit_zero`（**integration**）：一時プロジェクト＋
  file backend で、PSI が alert 帯になるよう**構成した**基準/配信データ（分布を大きくずらす＝期待 band は
  データの作り方から導出）→1 回目で課題が 1 件・2 回目でも 1 件のまま・exit code はどちらも 0。
- `test_monitor_file_issue.py::test_no_alert_no_issue`（**unit**）：同一分布（psi≈0＝alert 無し）では起票 0 件・
  exit 0。
- `test_monitor_file_issue.py::test_flag_off_unchanged`（**unit**）：`--file-issue` 無しでは issues ディレクトリに
  何も書かれない（既定の後方互換）。
- `uv run verify` 全体緑（coverage_lint・doclint を含む）。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：冪等判定の内容指紋が本当に決定的か＝2 回実測／exit code に alert が漏れて
いないか＝門番化の変異検査／既存 `data monitor` の出力が 1 行も変わっていないか）
