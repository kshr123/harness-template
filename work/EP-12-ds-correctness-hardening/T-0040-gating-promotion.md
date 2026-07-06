---
id: T-0040
kind: task
status: done
title: 合否・昇格の正しさ（passes の NaN・promote の向き・孤児 version）
created: 2026-07-05
verified_by:
  - tests/test_ds_eval.py::test_passes_nan_fails_closed
  - tests/test_ds_models.py::test_promotion_direction_resolved_from_registry
  - tests/test_ds_models.py::test_promotion_rejects_unknown_primary_and_contradicting_direction
  - tests/test_ds_models.py::test_orphan_version_dir_is_ignored
---
# T-0040 合否・昇格の正しさ

## 受け入れ基準
- `eval.passes` は指標が **NaN のとき不合格（fail-closed）**：合格条件を正の形（`>=`/`<=`）で 1 度だけ書き、
  満たさなければ落とす。higher_is_better の両向きで NaN が落ちること。
- `models.promote_model` の向きは **`eval.METRICS[primary].higher_is_better` から解決**する（呼び出し引数任せにしない）。
  `primary` が未登録なら明示エラー。`log_loss`/`rmse` を primary にしたとき、悪い方（損失が大きい方）を昇格しない。
- `models._versions` は **manifest を持つ版だけ**を列挙し、保存途中でクラッシュした孤児ディレクトリで
  `load_model(version=None)` が壊れない（manifest・promotion YAML も tmp→replace で原子的に書く）。

## 結果
実装・テスト先書き（pre-fix 失敗を確認）・独立レビュー・verify 緑で完了予定。詳細は `docs/ds-review-2026-07-05.md`。
