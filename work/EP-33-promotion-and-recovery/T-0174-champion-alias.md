---
id: T-0174
kind: task
status: done
title: champion の走査を版の刻みに限定し、異物 yaml は fail closed（ASCII 順の乗っ取りを塞ぐ）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0173, T-0175]
verified_by:
  - tests/test_promotion_rollback.py::test_ds_foreign_yaml_in_promotions_fails_closed
  - tests/test_promotion_rollback.py::test_agent_foreign_yaml_in_promotions_fails_closed
---
# T-0174 champion の走査を版の刻みに限定する

## 何が問題か
`champion()` は `sorted(promo_dir.glob("*.yaml"))[-1]` で「いちばん新しい昇格記録」を選び、それが指す版を
champion と見なす。`promotions/` に時刻名でない `.yaml` が 1 つでも入ると壊れる：
`sorted(['20260710T090000000000Z.yaml', 'notes.yaml'])[-1] == 'notes.yaml'`（数字は英字より前に並ぶ）。
`notes.yaml` に `version` キーがあれば**別の版が champion として配信される**（`serve/runtime.load_champion`
がこれを読む）。劣る版を指す手書き yaml を 1 枚置くだけで、黙って劣化版が配られる。

## やったこと
`_promotion_files(entity_dir, label=…)` を中核 `harness/promotion.py` に足し、`promotions/` の走査を
**ファイル名が版の刻み（`VERSION_FORMAT`）に一致するものだけ**に限定した。一致しない yaml が 1 枚でも居たら
`ValueError`（無視でなく失敗＝fail closed）。champion 解決（`_approved_records`）も履歴（`history`）も同じ
規則を共有する。時刻名は `datetime.strptime(stem, VERSION_FORMAT)` で判定する（別レジストリを増やさない）。

## 却下した対策（L-017 の適用記録）
当初案は `<entity>/aliases/champion.yaml` という**明示ポインタ（alias ファイル）**で champion を指し、
`promotions/` の走査自体をやめる、というものだった（MLflow が Model Stages を alias に移した先例）。却下した：

- alias ファイルは**現在の状態の写し＝台帳**で、promote / rollback のたびに原子的に書き直し、「alias.version が
  最新の approved 記録と一致する」という新しい不変量を別に守る必要が出る（L-021：自己申告の台帳は必ず古びる）。
  EP-31 の item.md が「版記録ファイルは写し＝台帳であり、必ず古びる」として fork の版記録を却下したのと同じ論理。
- 塞ぐべき実測欠陥は「異物 yaml による ASCII 順の乗っ取り」の 1 点。走査の限定＋異物拒否でこれは完全に塞がる。
  champion を動かす唯一の道は「approved 記録を追記する」ことだけになり、alias が防ぐはずの「履歴の追記で
  champion が勝手に動く」事象はそもそも起きない（追記＝明示の承認行為だから）。
- したがって alias ファイルは安全性を追加で買わないのに機構だけ増やす。増やさない。

## 受け入れ基準
- `promotions/` に `notes.yaml` を置くと `champion()` も `history()` も `ValueError` で止まる
  （ds・agent の両方。先に赤くなるのを確認：ガードを外すと `notes.yaml` を拾って例外なく別版を返す）。
- 正規の時刻名 yaml だけなら従来どおり動く（既存の characterization・rollback テストが無変更で緑）。
- `uv run verify` 全成功。
