---
id: T-0195
kind: task
status: done
title: 複製シミュレーションの CI 1 本（検出器と明記）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0193, T-0194]
verified_by:
  - tests/test_template_copy.py::test_ci_has_clone_simulation_detector
---
# T-0195 複製シミュレーション CI

## 何を
CI に `clone-simulation` ジョブを 1 本足す：現在のチェックアウトを clone → fork の設定 → `init-project` で
案件領域を白紙化＋profiles 空 → 素の `uv sync` → `uv run verify` が緑。これは上の 4 タスクが本当に効いている
ことの**実行可能な定義**。

## なぜ検出器だと明記するか
「`profiles = []` の複製で verify が緑」は構成から導ける受け入れ基準だが、テストが実状態を仮定する型の結合は
参照の grep では原理的に見えない。境界の実行可能な定義がこの 1 本しかないので置く（L-017：唯一の検出器として
正直に申告し、増やさない）。verify の実行時間に影響させないため CI の別ジョブにする。

## 受け入れ基準
- ci.yaml に clone-simulation ジョブがあり、init-project → uv sync → verify を回す（存在を test で固定）。
- `uv run verify` 全成功。
