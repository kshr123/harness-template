---
id: T-0082
kind: task
status: done
title: eda 完成度（KS/Wasserstein・mutual_information 表・leakage_scan）
created: 2026-07-06
depends_on: [T-0077]
verified_by:
  - tests/test_ds_eda.py::test_compare_ks_wasserstein_shift_monotone
  - tests/test_ds_eda.py::test_mutual_information_nonlinear_dependence
  - tests/test_ds_eda.py::test_leakage_scan_flags_suspects_with_reasons
  - tests/test_ds_eda.py::test_leakage_scan_multiple_target_copies_all_flagged
  - tests/test_ds_eda.py::test_leakage_scan_string_classification_target_mutual_information
---
# T-0082 eda 完成度

## 背景（次点部品・sklearn/scipy 素通し・DEC-0006/0010）
- **KS/Wasserstein**：PSI（ビン依存）の弱点を補完する標準の分布距離。scipy は sklearn 経由で既に環境にある＝新依存ゼロ。
- **mutual_information 表**：`correlations`（線形）の非線形補完。sklearn 委譲。
- **leakage_scan**：既存部品（id_like フラグ・correlations・category_target の 0/1 張り付き・duplicate_columns）の**合成のみ**で
  「目的変数を漏らしていそうな列」を洗う入口。新しい統計は書かない。

## 受け入れ基準（素通し・合成・DEC-0009 入口まで）
- `compare`（既存の分布比較）に KS 統計量・Wasserstein 距離の列を追加（scipy.stats.ks_2samp・wasserstein_distance）。psi は不変。
- `mutual_information(df, target, *, task, seed)`：sklearn の mutual_info_* で列→MI の構造化表（決定的・seed 明示）。
- `leakage_scan(df, target, *, ...)`：既存部品の合成で「怪しい列」に理由（高相関・0/1 張り付き・id 的・重複）を付けた表を返す。
  **新統計は作らない**。eda.py の「専用のリーク検出関数は作らない」docstring 方針を**転換**するので、docstring 更新＋learnings 1 行
  （DEC-0012＝方針転換は即記録。必要なら DEC も可だが最小は learnings＋docstring）。
- **DEC-0009**：関数は docstring で使い方。eda 系は CLI/eda スキルから導かれる（既存の導線に載せる。手書き一覧は作らない）。

## 触ってよいファイル
`src/harness/ds/eda.py`＋`tests/test_ds_eda.py`＋`docs/learnings.md`（leakage 方針転換 1 行）。`pipeline.py`/`eval.py`/`unsupervised.py` は
触らない（並行作業あり）。`psi`・`drift_auc` は変更しない（他が使う・不変）。

## 検査（テスト先書き・構成から導く）
- KS/Wasserstein：同一分布で ≈0・平行移動で単調増（構成から）。
- mutual_information：非線形依存（y=x² 等）で相関≈0 でも MI>0。線形依存で高 MI。決定的。
- leakage_scan：目的変数のコピー列・0/1 完全張り付き列・id 列を仕込んだデータで、それらが理由つきで挙がる。無害な列は挙がらない。

## 独立レビュー（maker≠checker・差分のみ・実測）
KS/Wasserstein（平行移動 d→wd==d 厳密・台離れ→ks==1・全欠損側 None）・mutual_information（y=x² で MI>0・決定的・定数 0）・
leakage_scan（合成のみ・4 理由・クリーン 0 行）を実測。psi/drift_auc 不変。方針転換を L-011 に即記録（DEC-0012）。
初回レビューで (c) 重複の推移律漏れ・(d) 文字列分類 target の弱さを検出→(c) 重複グループ解決で全コピー flag・(d) 新設 MI を合成した
high_mutual_information 理由で任意 target 型に対応（変異ガードテスト追加）。(a) CLI/スキル導線は T-0083 で配線。
(b) MI の random_state 変異は微小ジッタで決定的に殺せず docstring 明記で受容。入口配線は [[T-0083]]。
