---
id: T-0055
kind: task
status: done
title: datetime/cyclical 特徴ブロック（日時から year/month/dow/hour＋周期は sin/cos）
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_features.py::test_datetime_parts_are_polars_ranges
  - tests/test_ds_features.py::test_datetime_cyclical_month_unit_circle_and_wraparound
  - tests/test_ds_features.py::test_datetime_cyclical_hour_wraps_around_midnight
  - tests/test_ds_features.py::test_datetime_cyclical_weekday_wraps_and_anchors_monday
  - tests/test_ds_features.py::test_datetime_feature_names_match_output
  - tests/test_ds_features.py::test_datetime_rejects_unknown_part_and_cycle
---
# T-0055 datetime/cyclical 特徴ブロック

## 背景
日時列は生のままだと使えない（順序尺度でない・周期がある）。日付部分の抽出と、周期成分（月・曜日・時）の
sin/cos 符号化（12月と1月が近い＝不連続を消す）を標準ブロックとして出す。

## 受け入れ基準（polars の dt アクセサ素通し・手書きの暦計算をしない）
- `features.py` に無状態 `FeatureBlock` を追加（`Columns`/`Interactions` と同じ書き方）。API 例：
  `DateTimeFeatures(columns, parts=("year","month","day","weekday","hour"), cyclical=("month","weekday","hour"))`。
  - parts：各 datetime 列から `pl.col(c).dt.year()/.month()/.day()/.weekday()/.hour()` 等で整数列を出す
    （出力列名 `{c}_{part}`）。polars の weekday は 1..7（月曜=1）等、実際の値域を docstring に明記。
  - cyclical：周期を持つ part（month=12・weekday=7・hour=24 の**周期**）について `sin(2π·v/period)`・`cos(2π·v/period)`
    の 2 列（`{c}_{part}_sin`/`{c}_{part}_cos`）を出す。period はその part の値域から決める（値のオフセットに注意＝
    month は 1..12 なので (month-1)/12 等、ズレなく一周する形にし docstring に明記）。
  - `feature_names()` は出力列名を設定から確定（無状態なので fit 前でも返せる）。
- BLOCKS に登録（catalog `data blocks` に description つきで載る＝DEC-0009）。既存ブロック・build_estimator は不変。

## 触ってよいファイル
`src/harness/ds/features.py`（新ブロック＋BLOCKS 登録）＋`tests/test_ds_features.py`（無ければ既存の features テストに追加）。
`pipeline.py`/`eval.py`/`cv.py`/`models.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 既知の日時（例 2021-01-15 と 2021-12-15）で month/weekday/hour が正しい整数（polars の値域に従う）。
- cyclical：month=1 と month=13相当（=1 の一周後）で sin/cos が一致する連続性、month の sin²+cos²=1、
  12月と1月の距離が1月と2月の距離に等しい（周期性）を構成から確認。
- feature_names() が実際の出力列と一致（数・順序）。

## 独立レビュー（2026-07-06・maker≠checker）
異常なし（blocking/important ゼロ）。位相合わせ（weekday の -1 補正・12月↔1月・23時↔0時が隣接）・polars 値域
（weekday 1..7 月曜=1）・無状態 feature_names 整合・Date 型で大声で落ちることを実測で確認。minor 2 件を反映：
weekday の cyclical テストが無かった（暦バグの温床）→ 月曜アンカー＋週またぎ隣接テストを追加、Date 型（hour 不可）の
扱いを docstring に明記（「hour を外して使う」導線＝DEC-0009）。

## 結果
実装・独立レビュー（反映）・verify 緑で done。ideal-build-plan Wave 3。
