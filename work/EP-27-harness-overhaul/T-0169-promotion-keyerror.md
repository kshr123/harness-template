---
id: T-0169
kind: task
status: done
title: 昇格判定で現 champion に primary 指標が無いと KeyError になる欠陥を直す
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_ds_models.py::test_promotion_rejects_when_champion_lacks_the_primary_metric
  - tests/test_ds_models.py::test_promotion_rejects_when_candidate_lacks_the_primary_metric
  - tests/test_agent_store.py::test_promote_rejects_when_champion_lacks_the_primary_metric
  - tests/test_agent_store.py::test_promote_rejects_when_candidate_lacks_the_primary_metric
---
# T-0169 昇格判定の非対称な欠陥

## 事象
`promote_model`（`src/harness/ds/models.py`）と `promote_agent`（`src/harness/agent/store.py`）は、
**候補**の metrics に primary 指標が在るかは確かめる（無ければ ValueError）が、**現 champion** の metrics に
在るかは確かめずに `champ.metrics[primary]` と添字アクセスしている。過去の昇格と違う primary 指標で
昇格しようとすると `KeyError` が素通りする（契約に無い例外型で、CLI は `ValueError` しか捕まえない）。

`passes()` は「metrics 側に無い登録済みの名は不合格（測っていない＝満たしたと見なさない）」という規約を
持っている。比較の側だけがこの規約から外れている。

## やること
champion 側にも同じ規約を適用する。**測っていない指標では比較できない＝昇格しない**（fail closed）。
`ValueError` にして、どちらの側に無いのかをメッセージに書く。ds と agent の両方を直す（実装は 2 か所に
重複しているが、抽出は T-0171 で行う。ここでは欠陥だけを直して挙動を揃える）。

## 実測
テストを先に書き、`KeyError: 'log_loss'`（`src/harness/ds/models.py:492`）で失敗することを確認してから直した。
候補側に primary が無い分岐（`primary 指標 '…' が metrics に無い`）は実装はあったがテストが 1 本も無く、
到達したことが無かった。あわせて固定した。

## 受け入れ基準
- 現 champion の metrics に primary が無い状態で昇格しようとすると `ValueError`（`KeyError` ではない）。
  ds・agent の両方でテストする。
- 候補の metrics に primary が無いときの `ValueError`（既存の未テストの分岐）にもテストを足す。
- champion が動いていない（昇格していない）ことを確かめる。
- `uv run verify` 全成功。
