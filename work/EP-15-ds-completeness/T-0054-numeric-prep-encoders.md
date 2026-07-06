---
id: T-0054
kind: task
status: done
title: 数値前処理エンコーダ（scale/impute/missing_flags）＝kNN・線形が NaN で壊れる穴を塞ぐ
created: 2026-07-06
depends_on: [T-0048]
verified_by:
  - tests/test_ds_pipeline.py::test_scale_fixes_nan_hole_for_linear_model
  - tests/test_ds_pipeline.py::test_scale_standardizes_and_imputes_median
  - tests/test_ds_pipeline.py::test_impute_median_default_and_mean_override
  - tests/test_ds_pipeline.py::test_missing_flags_marks_cells_and_keeps_all_columns
---
# T-0054 数値前処理エンコーダ

## 背景（穴）
`columns` ブロックで数値列を素通しし encode を付けないと、kNN・線形モデルは NaN で落ちる。数値前処理を
標準の入口（ENCODERS）として出す（今は `_pca`/`_cluster` 内部に埋まっているだけで単独の入口が無い）。

## 受け入れ基準（すべて sklearn 素通し・DEC-0006）
- ENCODERS に登録（`pipeline.py`・既存 `_onehot` 等と同じ書き方・docstring 由来 description）：
  - `scale`：`Pipeline([SimpleImputer(strategy="median"), StandardScaler()])`（欠損を埋めてから標準化＝NaN 穴を塞ぐ）。
  - `impute`：`SimpleImputer`（strategy を params で選べる・既定 median）。埋めるだけが要るとき。
  - `missing_flags`：`MissingIndicator`（欠損の 0/1 列を足す＝欠損自体が予測に効く場合）。`features="all"` か既定かは
    実装時に無理のない形（列が消えない・空でも落ちない）を選び docstring に明記。
- `data encoders` カタログに 3 つが description つきで載る（DEC-0009）。既存エンコーダ・build_estimator の挙動は不変。

## 触ってよいファイル
`src/harness/ds/pipeline.py`（ENCODERS 登録部と factory）＋`tests/test_ds_pipeline.py`。
`eval.py`/`cv.py`/`features.py`/`models.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- NaN を含む数値列＋線形/kNN モデルの estimator が `scale` を挟むと fit/predict が通る（挟まないと NaN で落ちることも 1 本で対比）。
- `scale`：既知の平均・分散のデータで変換後が平均 0・分散 1（構成から）。欠損は median で埋まる。
- `missing_flags`：欠損のある/なし列で 0/1 が正しく立つ。列数が想定どおり増える。
- `impute`：strategy=median/mean で埋め値が構成から導ける。

## 独立レビュー（2026-07-06・maker≠checker）
異常なし（blocking/important ゼロ）。穴を実際に塞ぐこと・指定列だけに効くこと・missing_flags が全列非欠損でも落ちない
ことを実測で確認。minor 2 件を反映：scale の median テストが [0,10,0,10]（median=mean）で median/mean を判別できない
（金メッキ）→ [1,2,9]（median 2≠mean 4）で NaN 行＝観測値 2 の行と一致する判別式に。missing_flags 単独は元列が
置き換わる（値が model に届かない）旨と「値も残すなら impute を併記」を docstring に追記。

## 結果
実装・独立レビュー（反映）・verify 緑で done。ideal-build-plan Wave 3。
