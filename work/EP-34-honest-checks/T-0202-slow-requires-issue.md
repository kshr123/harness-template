---
id: T-0202
kind: task
status: done
title: slow マーカーに ISS 参照を必須化
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_conventions.py::test_slow_without_iss_reference_is_detected
  - tests/test_conventions.py::test_slow_with_iss_reference_is_ok
  - tests/test_conventions.py::test_skip_markers_include_slow
  - tests/test_conventions.py::test_check_collected_items_flags_slow_without_iss
  - tests/test_conventions.py::test_check_collected_items_accepts_slow_with_iss
  - tests/test_conventions.py::test_skipif_is_covered_and_pyramid_markers_are_ignored
---
# T-0202 slow マーカーに ISS 参照を必須化

## 背景
`checks.toml` の fast/standard/full の 3 段階はすべて pytest を `not slow` で回しており、`slow` を
回す段階が無い。一方 AGENTS のテストの決まりごとは「skip・xfail は課題（ISS-…）参照を必須にする」
（理由の無い skip 禁止）。`slow` はマーカーを付けるだけで理由なしに同じ「テストを永久に回さない」
効果を得られる＝skip/xfail に課した縛りの抜け道になっている。

## やったこと
`src/harness/testing.py` の `SKIP_MARKERS`（conftest の収集フックが ISS 参照必須にする対象マーカーの
集合。既存は `{"skip", "skipif", "xfail"}`）に `"slow"` を足した。この 1 行の変更だけで、既存の
`tests/conftest.py::pytest_collection_modifyitems` フック（`harness.testing.skips_without_iss` を呼ぶ）が
`slow` マーカーにもそのまま効く。**新しい検査コード・新しい書式は作っていない**（同じ関数・同じフックに
`slow` を合流させただけ）。

### なぜ `src/harness/conventions.py`（skip の理由必須検査）ではなく `testing.py`/`conftest.py` に足したか
タスク着手時の想定は「conventions.py にある skip の検査と同じ場所」だったが、調べると skip/xfail の
ISS 必須化は 2 か所に分かれている：
- `conventions.py`：**命令形の呼び出し**（`pytest.skip(...)` / `pytest.xfail(...)`）を ast で静的検査。
- `testing.py` の `SKIP_MARKERS` + `tests/conftest.py` の収集フック：**マーカー版**
  （`@pytest.mark.skip(reason=...)` 等）の ISS 参照を、pytest の `Item.iter_markers()` から実際に検査。
  （`conventions.py` の docstring 自身が「マーカー版は conftest+testing.py が担う」と明記している。）

`slow` には命令形（`pytest.slow(...)` のような呼び出し）が存在せず、常にマーカー（`@pytest.mark.slow`
または `pytestmark = pytest.mark.slow`）としてしか使えない。したがって対応する既存の仕組みは
`testing.py`/`conftest.py` 側であり、そこに合流させるのが「同じ関数・同じ書式に寄せる（2つ目の書式を
作らない）」を最も文字どおり満たす選択。`conventions.py` には対応する枝を**足していない**（足す先が無い
＝命令形が存在しないため）。ただし `conventions.py` の docstring には、slow の ISS 必須化がどこにあるかへの
参照を追記し、読み手が迷わないようにした。

## `pytestmark = pytest.mark.slow`（モジュール全体）も対象にするか＝決めた
**対象にする。** 理由：`tests/conftest.py` の収集フックは `item.iter_markers()` で得たマーカーを見ており、
pytest 自身の仕様として `Item.iter_markers()` は関数装飾のマーカーとモジュール直書きの `pytestmark` を
区別せず同じ `pytest.Mark` の形で返す。つまり実装コードは何も変えなくても両方に効く。この前提（pytest
本体の挙動）が今後変わっても検知できるよう、`tests/test_conventions.py` に pytester（pytest 標準の
自己テスト用フィクスチャ。`tests/conftest.py` に `pytest_plugins = ["pytester"]` で opt-in した）を使った
実データの回帰テストを足した（T-0210 で収集フックの正本を `harness.testing.check_collected_items` に
集約した際、これらは正本の関数を直接呼ぶ形へ置き換えた）：
`test_check_collected_items_flags_slow_without_iss` / `test_check_collected_items_accepts_slow_with_iss`。

## なぜ `slow` を回す CI job を足さないか（やらないことの理由）
独立レビューで確定した制約。実測で `slow` マーカー付きのテストは現在 0 件。0 件の集合に対して
`pytest -m slow` のような job を足すと、pytest は該当テストなしで **exit code 5** を返す。CI がこれを
素朴に「実行できた＝合格」として扱うと、job は常に「該当 0 件＝合格」という何も保証しない緑を出し続ける
（テストが増えても勝手には検出されない・気づかれない張りぼて）。`checks.toml` の段階から `not slow` を
外すことも、この理由により行わない。ISS 必須化（発生源の封鎖）だけで、抜け道は塞がる。

## AGENTS.md への追記
テストの決まりごとの「skip・xfail は課題（ISS-…）参照を必須にする」の項に、`slow` も同様である旨を
1 行追加した。

## 受け入れ基準
- ISS 参照の無い `@pytest.mark.slow` / `pytestmark = pytest.mark.slow` は pytest の collect でエラーになる。
- ISS 参照つきの `slow` は通る（skip/xfail と同じ書式：`reason=` キーワードまたは位置引数の文字列に
  `ISS-<番号>`）。
- 既存の skip/xfail の検査（命令形・マーカー版どちらも）は壊れていない。
- `uv run verify` が全成功する。
