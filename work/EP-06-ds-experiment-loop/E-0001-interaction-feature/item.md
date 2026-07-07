---
id: E-0001
kind: experiment
status: done
plan: detailed
title: 交互作用特徴量 x1*x2 で予測が改善するか
requirements: [REQ-004]
depends_on: [T-0013, T-0014]
closed: 2026-07-03
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_smoke
  - tests/test_e2e_experiment.py::test_e0001_two_variants_share_folds
created: 2026-07-03
owner: sakurada
---
# E-0001 交互作用特徴量 x1*x2 で予測が改善するか

詳細は SPEC.md、実行体は code/train.py、設定は config.yaml。データ生成→特徴量→交差検証→合否→
store 保存（fold=split・OOF=processed）→モデル保存（Pipeline 丸ごと）→results を一気通貫で回す。
**この実験は以後の実験のコピー元（雛形）**：train.py を `build_estimator`（config 駆動）ベースに変更（EP-08/T-0022・指標は不変）。
code＋config の正本は `templates/experiment/`（T-0140 で移設）。schema 定義（e0001_*.yaml）も
`templates/experiment/data/` へ移設（T-0141＝雛形の完全自己完結）＝再現記録は results/ が保持。

## 結論
**棄却**：交互作用特徴量 x1*x2 は採択しない。本規模（n=2000・n_folds=5・両変種は同一分割で比較）の
OOF ROC-AUC は baseline 0.98565 に対し interaction 0.98560（差 −0.00005・採択基準 +0.01 に遠く届かない）。
合成データは 1.5*x1 − 2*x2 + 雑音 の線形生成なので交互作用が効かないのは見込みどおり。
**棄却でも done**＝「負の結果も記録で完了」の実地確認まで含めて本実験の完了条件（詳細は results/summary.yaml）。
