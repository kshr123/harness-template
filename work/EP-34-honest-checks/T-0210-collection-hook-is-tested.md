---
id: T-0210
kind: task
status: done
title: 収集フックの正本を harness.testing に集約し、本物の conftest を end-to-end で検証する
created: 2026-07-10
depends_on: [T-0202]
verified_by:
  - tests/test_conventions.py::test_real_conftest_errors_on_slow_without_iss
  - tests/test_conventions.py::test_real_conftest_accepts_slow_with_iss
  - tests/test_conventions.py::test_real_conftest_errors_on_unmarked
  - tests/test_conventions.py::test_check_collected_items_flags_slow_without_iss
  - tests/test_conventions.py::test_check_collected_items_accepts_slow_with_iss
  - tests/test_conventions.py::test_check_collected_items_flags_unmarked
---
# T-0210 収集フックの正本を 1 か所にし、本物の conftest を end-to-end で検証する（T-0202 の追補）

## 何が問題か（独立レビューが実測・2026-07-10）
`tests/conftest.py` の `pytest_collection_modifyitems`（unit/integration/e2e の付け忘れ＋skip/slow の ISS 参照
必須）を壊しても、**911 テストが緑のまま**だった（M6）。その状態で ISS 参照の無い `pytestmark = [unit, slow]`
を置くと素通りする。

原因：T-0202 が足したテストは、conftest の抽出ロジックを**テスト側に複製した `_extract_skip_markers`** を
検証していた。本物のフックが素通りになっても、複製は正しく動き続ける。**本物のフックを一度も検証していない**
（2 つ目の正本ができていた）。

## なぜテスト側の複製が問題か
論理の正本が 2 か所（本物の conftest と、テスト内の `_extract_skip_markers`）に分かれると、テストは複製の方を
守る。本体が退化しても複製が緑を出すので、テストは「本体が動く保証」を与えない。保証の (b) を名乗るには、
**テストの対象が本物の実行経路そのもの**でなければならない（そうでなければ (c)＝人が気をつける、と同じ）。

## 直し方
- 収集フックの中身（マーカー抽出＋`skips_without_iss`／`unmarked` の呼び出し＋エラーの出し方）を
  `harness.testing.check_collected_items` の 1 関数に出し、`tests/conftest.py` はそれを呼ぶだけの委譲にする
  （論理の正本を 1 か所に）。
- **本物の `tests/conftest.py` を持ち込んだ end-to-end のテスト**を書く：`pytester` に本物の conftest の中身を
  `makeconftest` でコピーし、ISS 参照の無い `slow`（および無印テスト）を置いたときに `runpytest` の collect が
  ERROR になることを終了コードで確かめる。この経路は本物の conftest → 本物の
  `harness.testing.check_collected_items` を通るので、どちらを壊しても RED になる。
- テスト側の複製 `_extract_skip_markers` は削除する（2 つ目の正本を残さない）。

## 受け入れ基準
- `tests/conftest.py` の抽出、または `harness.testing.check_collected_items` を壊すと、上記 end-to-end テストが
  RED。これをミューテーションで実測して記録する（M6 が緑だった箇所が RED になること）。

## ミューテーション実測
`harness.testing.check_collected_items` の抽出・呼び出しを壊すと end-to-end テストが RED になることを実測して
記録する（本文の「実測」節）。
