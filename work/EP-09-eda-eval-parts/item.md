---
id: EP-09
kind: epic
status: done
title: EDA と評価の部品（構造化レポート・指標レジストリ・分布差・重要度）
plan: detailed
requirements: [REQ-004]
created: 2026-07-03
closed: 2026-07-03
---
# EP-09 EDA・評価の部品（エージェントファースト・テスト先行）

## 目的
実験ループ（EP-06〜08）の上に「データを見る（EDA）」と「結果を深掘る（評価）」の部品を載せる。
参考リポ（`draft/reference/ml-competition-template-main` の eda/・evaluation/・domain/）の実質を、
本プロジェクトの流儀（sklearn を再発明しない・図でなく構造化レポート・入口まで作って完了）に翻訳する。
目的はコードでなく、**将来のエージェントが再コーディングせず config とスキルで EDA・評価を回せる土台**。

## 進め方（テスト先行＋先コミット。各タスクは「赤テスト→実装→独立レビュー→verify緑」を1タスク内で）
**詳細設計は `DESIGN.md`（正本・Fable 設計）**。全体像・型シグネチャ・入口・テストピラミッド・横断判断・
「あえて作らない」一覧はそちらを見る。**採用した既定**（利用者確認済み）：
- **正本は1つ・ビューは2つ**（利用者指摘「EDA は人も見る」を反映・改訂1）。正本＝検査済みの `eda`/`analysis`/`eval`
  関数＋`uv run data profile/compare` の YAML（エージェントが読む・決定的）。人のビュー＝`notebooks/eda.py`（marimo
  の薄い雛形・同じ関数を呼んで表と図を出すだけ・数値ロジックと結論は書かない）。腐り防止＝e2e スモークが
  `python notebooks/eda.py` をヘッドレス実行（終了コード0のみ検査・図の画素は比較しない）。依存は ds extra に
  `marimo`・`altair`。図の専用モジュール（巨大 visualizer）は作らない（Rule of Three）。
- **回帰経路を入れる**（`MODELS` に ridge 1行＋回帰の統合テスト。回帰指標を「入口の無い部品」にしない）。E-0001 は無変更。
- **未確定（着手を止めない）**：notebook の HTML 書き出し（非 Python 閲覧者向け）は既定「しない」（見る人は `marimo run`）。
  上書き＝Python 環境を持たない関係者に配る案件なら `marimo export html` を results/ に手動で置く（門番外）。

**着手順は「歩く骨組みを先に1本通す」**（`docs/method.md`）。1と2が終われば EDA も評価拡張も端まで一巡し、以降は緑を保った追加：
1. **T-0024 eval.py METRICS 背骨**：METRICS レジストリ（分類＋回帰・向き付き）・evaluate 系・passes の向き対応・
   `uv run data metrics`・test_catalog 延長。既存の dict 完全一致テストを部分集合確認へ直す（additive）。
2. **T-0025 eda.py profile**：profile / target_summary / to_dict＋`uv run data profile <table_id>`＋**eda スキル新設**。
   調査 kind（investigation）との接続もここで書く。
3. **T-0026 eda.py 比較・分布差**：correlations / high_correlation_pairs / compare / psi＋`data compare`、
   さらに drift_auc（run_cv 合成）＋`data compare --auc`。eda スキルに「0.7 目安→原因調査」を追記。
4. **T-0027 analysis.py 深掘り**：segment_metrics / worst_rows / permutation_importance / cv_permutation_importance＋
   experiment スキルに「結果の深掘り」節。drift の原因列特定もここで閉じる。
5. **T-0028 回帰経路**：run_experiment(task=)＋MODELS に ridge＋回帰の統合テスト（指標の死蔵防止）。

## やらないこと（DESIGN §7 の要点・Rule of Three）
ノートブック（marimo/jupyter）・図生成モジュール・検定群（KS/カイ二乗）・モデル固有の重要度（LightGBM 導入時）・
回帰の2本目雛形の先回り作成・EDA レポート専用の保存形式。いずれも必要になった案件で足す。
