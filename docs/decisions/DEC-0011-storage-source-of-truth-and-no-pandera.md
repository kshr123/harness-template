---
id: DEC-0011
status: accepted
date: 2026-07-05
---
# DEC-0011 保存4作法の正本は harness/storage.py・検証は pandera を採らず polars で自前

## 状況（何を決める必要があったか）
DEC-0010（理想形を今作る）に基づく Wave 2（EP-14）で、(1) store.py/models.py/schema.py にコピペで重複していた
「保存の4作法」（URI 解決・原子書き込み・sha256 指紋・manifest 読み書き）の正本をどこに置くか、(2) `schema.validate` の
手書き検証を pandera へ移すか自前で高度化するか、を決める必要があった（ISS-0006・ISS-0010）。

## 検討した選択肢
- 保存：(A) 各ファイルにコピペを残す（現状）／(B) ds に artifacts.py を作る／(C) core に storage.py を作る。
- 検証：(D) pandera.polars に移す／(E) YAML 正本のまま polars で自前評価する。

## 決定と理由
- **保存＝(C)**：`harness/storage.py`（core・stdlib＋yaml のみ・polars/sklearn 非依存）に4作法の正本を置き、
  store/models/schema はそれを呼ぶ薄い方針層にする。URI の正本は既に core の config なので core が自然。
  指紋は `hashlib.file_digest`（ストリーム・全読みしない）。非 `file:` URI は3箇所とも `UnsupportedURIError` で
  fail-loud に統一（schema の黙示フォールバックを廃止）。S3/DWH は storage に1分岐足すだけで3呼び手は無変更になる。
- **検証＝(E)**：pandera は採らない。理由：(1) EP-12 で塞いだ4穴（Datetime パラメタ型・NaN≠null・複合 primary key・
  null 込み一意）は pandera.polars の既定と 1:1 対応せず、移行は回帰リスクだけ払って機能はほぼ増えない。(2) `checks`
  （cross-column 含む）は polars の `pl.sql_expr` で**依存ゼロ**で評価できる＝標準への委譲であり再発明でない（DEC-0006 と整合）。
  YAML を正本に保つ枠は不変。参考リポ(実践MLOps)は pandas＋pandera を使うが、当リポは polars ネイティブで既に穴を持たない。

## 影響（良い点・悪い点・これからやること）
- 良い点：保存の修正が1箇所で済み S3 着手が容易。`schema.checks` が「パースするだけ」の誤った安心から実評価へ（ISS-0010 解消）。
- 悪い点/注意：storage の `atomic_write` は writer が None を返す契約（strict 型の呼び手は None 返しラッパで包む）。
  非 file: の metadata URI を書いた複製先は schema 読みが例外になる（fail-loud・告知事項）。`checks` を「効くと誤解して」
  書いた既存 YAML はこの変更で初めて落ち始める（それが目的）。
- これからやること：pandera が本当に要る案件（統計的仮説・スキーマ推論・lazy 全件レポート）が出たら、YAML から
  `to_pandera(TableSchema)` を導出する口を足す（ideal-build-plan にスケッチあり）。本 DEC は撤回でなく拡張で対応する。
