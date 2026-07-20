---
id: T-0233
kind: task
status: done
title: checks.toml 不存在を ValueError に（verify 土台の最後の fail-open を閉じる）
created: 2026-07-20
closed: 2026-07-20
depends_on: []
verified_by:
  - tests/test_verification_mechanism.py::test_checks_config_rejects_missing_file
  - tests/test_verification_mechanism.py::test_run_check_rejects_missing_config_before_pytest
---
# T-0233 checks.toml 不存在を fail-closed に

`_verify_checks_config` は checks.toml が無いと寛容に return し、ruff/mypy/pytest を 1 つも走らせないまま
verify が緑になった（黙って全テスト層を失う）。クローンは checks.toml を必ず同梱するので「複製直後で無い」
は起きない＝寛容の根拠が無い。不存在を ValueError にして、存在と必須言語検査を要求する一本道に乗せた（条件1）。
