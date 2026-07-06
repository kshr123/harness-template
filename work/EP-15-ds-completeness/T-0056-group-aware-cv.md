---
id: T-0056
kind: task
status: done
title: group-aware CV（StratifiedGroupKFold/GroupKFold）＝同一グループの行を跨がせない
created: 2026-07-06
depends_on: [T-0051]
verified_by:
  - tests/test_ds_cv.py::test_make_folds_group_no_leak
  - tests/test_ds_cv.py::test_make_folds_stratified_group_keeps_balance_and_no_leak
  - tests/test_ds_cv.py::test_make_folds_group_by_none_matches_sklearn_kfold
---
# T-0056 group-aware CV

## 背景
同じ実体（ユーザ・店舗等）が複数行にまたがると、素の KFold/StratifiedKFold は同じグループを train と valid に
分けてリークする。sklearn の GroupKFold / StratifiedGroupKFold で「グループ単位」に分割する口を足す。

## 受け入れ基準（sklearn 素通し・DEC-0006）
- `make_folds`（`cv.py`）に `group_by: str | None = None` を追加：
  - group_by 指定かつ stratify_by 指定 → `StratifiedGroupKFold`（層化しつつグループを跨がせない）。
  - group_by のみ → `GroupKFold`（グループを跨がせない）。
  - どちらも未指定 → 現状（KFold/StratifiedKFold）で**完全に不変**。
  - shuffle/random_state の扱いは各 splitter の API に従う（GroupKFold は shuffle 引数を持たない版があるため、
    バージョン差を見て無理のない形に・再発明しない）。既存 make_folds の署名互換（キーワード追加のみ）。
- fold の DataFrame 形式・`fold_indices` との連携は現状のまま（fold 列を返す既存の形）。

## 触ってよいファイル
`src/harness/ds/cv.py`（make_folds まわりのみ）＋`tests/test_ds_cv.py`。
`eval.py`/`pipeline.py`/`features.py`/`experiment.py` は触らない（並行作業あり）。必要な変更が出たら報告のみ。

## 検査（テスト先書き・構成から導く）
- group_by 指定時、**どの fold でも同一グループが train と valid の両方に出ない**ことを全 fold で確認（リーク無しの核）。
- stratify_by + group_by 併用で、各 fold のクラス比が概ね保たれる（層化が効く）かつグループ非跨ぎ。
- group_by 未指定は既存テストが不変で緑（回帰なし）。
- 乱数は `seed=` 明示・グローバル種禁止。

## 独立レビュー（2026-07-06・maker≠checker）
異常なし（blocking/important ゼロ）。リーク無し（make_folds→fold_indices で train∩valid のグループ＝空）を実測で確認。
minor 3 件を反映：group_by=None の一致テストが自己比較（トートロジー）→ sklearn KFold を独立オラクルに比較する形へ、
層化+group の許容 ±0.15 のコメントが算術的に不正確 → 「陽性率は {0,1/3,2/3} のみ・±0.15 は完全層化要求」に是正、
StratifiedGroupKFold はグループ構造次第で層化非保証・グループ数<n_folds は sklearn が ValueError の旨を docstring に追記。

## 結果
実装・独立レビュー（反映）・verify 緑で done。ideal-build-plan Wave 3。
