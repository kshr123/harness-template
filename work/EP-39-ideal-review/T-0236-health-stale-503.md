---
id: T-0236
kind: task
status: done
title: /health に champion 記録との突合を入れ、不一致で stale＋503（切り戻しを配信の実体まで届かせる）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_serve_app.py::test_health_reports_stale_503_when_champion_changed_under_running_server
  - tests/test_serve_app.py::test_health_pinned_version_does_not_flag_stale
---
# T-0236 /health の champion 突合（stale＋503）

version 指定なし（現 champion 配信）で起動したサーバは、切り戻し・再昇格の後も走行中は古い版を配り続け、
検出は「人が再起動を覚えている」だけだった。/health が毎回ディスクの champion 記録と載っている版を突き合わせ、
食い違えば status=stale・HTTP 503 を返す。503 で k8s readinessProbe / compose healthcheck が配信を自動で外す
＝切り戻しが機構で配信の実体まで届く。version 明示起動（意図した固定）は突合しない。docs/serve.md の契約も更新。
