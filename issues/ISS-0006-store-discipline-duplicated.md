---
id: ISS-0006
kind: risk
state: open
found_in: ds-review-2026-07-05
created: 2026-07-05
title: 保存の「4作法」が store/models/schema にコピペで重複し、既に乖離している
---
# ISS-0006 保存の「4作法」が store/models/schema に重複し乖離している

## 事象
URI 解決（`file:` 前提・他は NotImplementedError）／tmp→rename の原子書き込み／sha256 指紋／manifest YAML の
読み書き、という「4作法」が `store.py`（`_local_base`/`save`）・`models.py`（`_base`/`save_model`）・`schema.py`
（`_project_dir`）に手でコピペされている。既に乖離：models は manifest を最後に書き load 時に指紋照合するが、
store は当時どちらもしていなかった（EP-12 で store 側の原子性は補修）。`schema._project_dir` は非 `file:` URI を
**黙って** `docs/data` にフォールバックし、他 2 箇所（NotImplementedError）と不一致。

## 根拠・影響
`docs/structure-review-2026-07.md` §中⑧が「store/models の4作法を docs/ へ」＝抽象化を **2 つ目のドメイン（Rule of
Three）まで保留**と決めている。本レビュー（2026-07-05）は同じ重複を **2 回目** に確認した＝3 回目で昇格の合図。
S3/DWH アダプタ（ISS-0001）着手時に 3 箇所を同時に触ることになり、乖離が広がる。

## 対処の方針（決めてから）
`harness/ds/artifacts.py`（または core の `harness/storage.py`。config が既に URI を持つ）へ
`resolve_uri`/`atomic_write`/`fingerprint`/`read_manifest`/`write_manifest` を抽出し、store・models・schema を薄い
方針層にする。非 `file:` URI の扱いも 1 箇所へ統一（fail-loud）。着手は S3 アダプタか 2 つ目のドメインが出た時。
