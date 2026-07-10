---
id: T-0176
kind: task
status: done
title: 初回昇格が NaN を止めない欠陥を直し、GateResult の欄名と中身のずれを解消する
created: 2026-07-10
depends_on: [T-0172]
verified_by:
  - tests/test_gates.py::test_value_threshold_rejects_a_non_finite_value
  - tests/test_gates.py::test_change_threshold_rejects_a_non_finite_candidate_even_without_a_baseline
  - tests/test_gates.py::test_change_threshold_names_a_non_finite_baseline_distinctly
  - tests/test_gates.py::test_evaluate_rejects_a_spec_without_a_kind
  - tests/test_gates.py::test_evaluate_rejects_an_unknown_gate_parameter_as_a_value_error
  - tests/test_gates.py::test_gate_results_record_the_parameters_they_were_given
  - tests/test_promotion_characterization.py::test_ds_a_non_finite_metric_never_becomes_champion
  - tests/test_promotion_characterization.py::test_agent_a_non_finite_metric_never_becomes_champion
---
# T-0176 判定の fail closed を実際に成立させる

独立レビュー（2026-07-10・T-0169〜T-0172 対象）の指摘への対応。

## 重大：`gates.py` の docstring が嘘だった
「判定はすべて fail closed。NaN はどの比較も False になり必ず不合格になる（発散したモデルが champion に
上がらない）」と書いてあるのに、`change_threshold` の `no_baseline` 分岐は**候補の値を一度も見ずに
`passed=True`** を返す。

失敗の筋道：champion 不在・`thresholds={}` で primary が NaN の版を昇格させると、
`value_threshold` は 1 件も課されず、`change_threshold` は「比較対象が無い」として通る。
NaN を測った版が champion になる。そして一度 NaN champion が生まれると、以後どの候補も改善量が NaN に
なって永久に昇格できない（`0.90 > NaN` は False）。記録を手で消す以外に復旧手段が無い。

抽出前から在った挙動で、T-0170 の characterization テストがこれを「仕様」として写し取っていた
（`# 閾値なしなので NaN でも初回昇格できる`）。characterization テストは**現状を写す**ものなので、
写したこと自体は正しい。写した結果として欠陥が可視になった＝目的どおり機能した。ここで挙動を変える。

`inf` も同じ穴を通る（`inf >= 0.8` は True）。だから合格条件を「NaN でない」ではなく
**「有限である」**（`math.isfinite`）で正の形に書く。発散は NaN だけでなく inf でも起きる。

## あわせて直すもの（同レビューの軽微な指摘）
- `reason="below_limit"` は向きが小さいほど良い指標で誤称（`log_loss=0.51` が上限 0.50 を超えて落ちても
  「下限割れ」と記録される）。`reason` は構造照合に使う設計なので、向きに依らない `threshold_not_met` にする。
- `GateResult.limit` は `change_threshold` では `min_change` を入れていた。欄名と中身が違う。
  判定ごとに引数が違うので、`params`（その判定に渡した引数）に一般化する。将来の判定（公平性・遅延）でも
  監査記録がそのまま書ける。
- `evaluate` の docstring が「未知の引数は ValueError」と書いていたが実際は **TypeError**。
  CLI は `except ValueError` しか捕まえないので、config から判定を書けるようにした瞬間に typo が
  トレースバックになる。`inspect.signature(...).bind` で呼ぶ前に検査して ValueError にする。
- `kind` の無い spec は `resolve(None)` に落ちていた。spec の欠落として先に止める。

## 受け入れ基準
- 閾値を 1 つも宣言せずに NaN／±inf の版を昇格させようとすると却下される（ds・agent の両方）。
- `value_threshold` が `inf`（大きいほど良い指標）・`-inf`（小さいほど良い指標）を通さない。
- `GateResult.params` に、その判定に渡した引数がそのまま入る。
- 未知の引数・`kind` の無い spec が `ValueError`（`TypeError` でない）。
- `uv run verify` 全成功。

## 記録の訂正（T-0172）
T-0172 の作業記録に「候補が primary を測っていない検査を、抽出時に落としていた」と書いたが、
`git show f7656f1` の時点で `promote_*` 側の `if primary not in record.metrics` は**残っていた**。
素通りしていたのは `gates.change_threshold` を直接呼ぶ経路だけで、`main` の昇格経路は一度も壊れていない。
実際より深刻に書いた。訂正する。
