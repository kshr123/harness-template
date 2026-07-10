---
id: T-0174
kind: task
status: todo
title: champion の正本を aliases/champion.yaml にする（昇格記録の走査をやめる）
created: 2026-07-10
depends_on: [T-0173]
verified_by: []
---
# T-0174 champion を alias で指す

## 何が問題か
`champion()` は `sorted(promo_dir.glob("*.yaml"))[-1]` で「いちばん新しい昇格記録」を選び、それが指す版を
champion と見なす。これは 2 つの点で壊れている。

1. **昇格記録（履歴）と champion（現在の状態）を同一視している。** 履歴は追記され続ける台帳で、現在の状態は
   1 つのポインタ。同じものではない。MLflow Model Registry が Model Stages を非推奨にして alias に移したのは
   同じ理由（2.9）。
2. **ファイル名の辞書順に依存している。** `promotions/` に時刻名でない `.yaml` が 1 つでも入ると壊れる。
   `sorted(['20260710T090000000000Z.yaml', 'notes.yaml'])[-1] == 'notes.yaml'`（数字は英字より前に並ぶ）。
   `notes.yaml` に `version` キーが無ければ `KeyError`、あれば**別の版が champion として配信される**。
   `README.yaml` でも `denylist.yaml` でも同じ。配信（`serve/runtime.load_champion`）がこれを読む。

現在の状態を「履歴の最大値」で毎回計算し直すのをやめ、明示のポインタにする。

## 構造
`<entity>/aliases/champion.yaml`（`storage.write_manifest` で原子的に書く）:

```yaml
alias: champion
version: 20260710T090000000000Z   # 現 champion の版
record: 20260710T090000000000Z.yaml  # この状態を作った昇格記録
updated: 2026-07-10T09:00:00+00:00
```

昇格記録（`promotions/<decided>.yaml`）に足す欄:
- `kind`: `promotion` | `rollback`（T-0175 で rollback が入る）
- `status`: `approved` | `rejected`（SageMaker Model Registry の `ModelApprovalStatus` の語彙）
- `rollback_to`: 切り戻し先の記録ファイル名（null＝戻り先が無い＝初回昇格）
- `gates`: 判定 1 件ずつの結果（`GateResult` の写し。監査用）

`previous_version`（既存）は「この記録が効く直前の champion の版」＝監査の欄。`rollback_to` は
「この記録から切り戻すときに戻る先」＝操作の欄。昇格記録では両者が一致するが、切り戻し記録では一致しない
（T-0175）。だから 1 つの欄で兼ねない。

`champion()` は alias だけを読む。`promotions/` は走査しない（追記専用の台帳になる）。

## 受け入れ基準
- `promotions/` に `notes.yaml` を置いても `champion()` が正しい版を返す（**先に赤くなるテストを書く**）。
- alias が指す版の実体が無ければ ValueError（既存の検査を保つ）。
- alias が無く昇格記録もない＝`None`（初期状態）。
- `serve` の champion 解決が壊れない（`load_champion` の e2e）。
- `uv run verify` 全成功。
