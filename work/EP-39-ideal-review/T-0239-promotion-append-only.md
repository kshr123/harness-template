---
id: T-0239
kind: task
status: done
title: promotion 記録の書き込み口を追記専用にする（刻み検証＋既存上書き拒否）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_promotion_rollback.py::test_write_record_rejects_non_version_decided
  - tests/test_promotion_rollback.py::test_write_record_is_append_only
---
# T-0239 promotion 書き込み口の追記専用化

読み側（_promotion_files）は版の刻みでない yaml で全読み込みを止めるほど徹底 fail-closed なのに、書き側
（_write_record）は刻みも既存衝突も無検査で、呼び手のバグや stats.adopt の公開 decided 引数で監査記録が黙って
消えうる。_write_record で decided の刻みを strptime で検証し、既存ファイルへの上書きは ValueError（追記専用）。
