---
id: T-0238
kind: task
status: done
title: retrain 雛形の continue-on-error 助言を削除し、却下（緑）と故障（赤）を exit code で分離
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_ci_lint.py::test_retrain_template_separates_rejection_from_failure
---
# T-0238 retrain 雛形の却下/故障の分離

複製先に渡る retrain 雛形が、同リポの audit ジョブでは禁止済みの fail-open（continue-on-error＝全故障を無音化）を
逆に勧めていた。雛形は使い方を教える媒体なので誤りが複製先へ増幅する。promote_model を try で囲み、PromotionError
（意図した却下）だけ握って理由をログに出し exit 0、他の例外（metrics 欠落・依存破損・バグ）は握らず赤。docs/ops.md 追随。
