# templates/schedule — time-based routine の雛形（agent monitor の定期実行）

`agent monitor`（実行ログの拒否/打ち切り率・コスト分位・ツール頻度を見る監視表）を、時間間隔で
定期実行するための GitHub Actions workflow 雛形。**実行しない資産**なので、構造（トリガ・停止宣言・
参照する CLI サブコマンド）の整合は schedule_lint（`src/harness/agent/schedule_lint.py`）が
`uv run verify` のたびに構造検査して腐りを止める。実行基盤（GitHub Actions・cron・Claude 側の
`/loop`・`/schedule` スキル等）は利用者環境が持つ（ハーネスは再発明しない・DEC-0006/0008）。

## コピー手順

1. このフォルダの `monitor.yml` を案件リポジトリの `.github/workflows/` へコピーする
   （**このリポジトリ自身の `.github/workflows/` には置かない**＝実 schedule を動かさない）。
2. `on.schedule` の `cron` を案件の運用に合わせて調整する（UTC・5 フィールド）。
3. `uv run agent monitor --file-issue` の対象ログ（既定 `artifacts/agent/runs/**/*.jsonl`）が
   案件の置き場と合っているか確認する（違えば `--log` を追加する）。
4. コミット・push すると、次の cron 起動（または `workflow_dispatch` の手動実行）から有効になる。

## 停止（stop）

「止め方の無い routine を作らない」の運用側の宣言。次のいずれかで止める：

1. GitHub の Actions 画面でこの workflow を開き **Disable workflow** を選ぶ。
2. または CLI で `gh workflow disable agent-monitor-routine`。
3. または `.github/workflows/monitor.yml`（コピー後のファイル）自体を削除する。

補足：GitHub は **60 日間 push が無い（=活動が無い）scheduled workflow を自動的に無効化する**
（意図せず動き続けることは無いが、能動的に止める手段は上の 3 つ）。

起票後の流れ（後半円＝issue→修正→検証緑で close）は `docs/agent.md` の「proactive 閉ループ」小節を参照。
