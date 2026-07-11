---
id: T-0185
kind: task
status: done
title: 判定を足す人が黙って壊せる 2 か所を塞ぐ（params の不変化・判定の第 1 引数の検査）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0179]
verified_by:
  - tests/test_gates.py::test_gate_result_is_hashable_and_params_are_read_only
  - tests/test_gates.py::test_registering_a_gate_without_a_context_first_argument_is_rejected
---
# T-0185 GATES の拡張時に黙って壊れる 2 か所

T-0179 の独立レビューが実測した軽微な指摘 2 件。どちらも**今の 2 判定では実害が無く、
3 つ目の判定を足す人が踏む**。EP-29 は収束の判定を、EP-30 は住人を足すので、その前に塞ぐ。

## 1. `ctx` を第 1 引数に取らない判定が、登録も実行もできてしまう
`gates._run` は `inspect.signature(factory).bind(ctx, **params)` で束ねる。`ctx` を**位置引数**として
渡すので、`def sneaky(metric, *, limit)` のような判定を登録すると `GateContext` が `metric` に束縛され、
**エラーを出さずに走る**（実測：`metric='GateContext(candidat…'` という結果が黙って返った）。
位置引数を 1 つも取らない判定だけは `ValueError`（too many positional arguments）で止まる。

判定の契約は「第 1 引数は `GateContext`」なので、`GATES.register` の時点で確かめる（fail closed）。
実行時に黙って壊れるより、登録時に `ValueError` で止める方が発生源に近い。

## 2. `GateResult.params` は frozen dataclass なのにハッシュ不能・中身が可変
`frozen=True` は `__hash__` を生成するが、`params` の実体が dict なので `hash()` も `set` への投入も
`TypeError: unhashable type: 'dict'` になる（実測）。等価比較は正常に効くのでテストは緑のまま通る。
さらに `result.params["limit"] = 999` が通る＝frozen が中身を守っていない。

昇格記録へ写して監査に使う欄なので、書き換えられない形にする。

## 受け入れ基準
- 第 1 引数が `GateContext` でない判定は `GATES.register` が `ValueError` で拒む。
  期待値は入力の構成から導ける（「`ctx` を取らない関数を登録しようとした」→拒否）。
- `GateResult` が `set` に入れられる（`hash()` が通る）。`params` の中身は書き換えられない。
- 既存の 2 判定・既存テストは 1 行も変えずに全成功（挙動を変えないことの証拠）。
- ミューテーション：上の 2 つの guard をそれぞれ外すと、対象テストが RED になることを実測する。
- `uv run verify` 全成功。

## やらないこと
- `GateContext` を keyword-only にする等、判定の署名そのものを変えること（既存 2 判定の書き換えになる）。
