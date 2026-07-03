---
name: eda
description: データを見る（探索的データ分析・EDA）際に自動参照。テーブルの概要・目的変数・欠損・train/test の違いを、図でなく構造化レポート（YAML）で把握し、人は marimo で見る。EDA・探索・データ確認・分布・欠損・目的変数・train/test 比較の語で発火。
---

# eda（データを見る＝構造化レポートが正本・人は marimo で見る）

正本は**検査済みの関数と YAML**（エージェントが読む・決定的）。人が見る図表は `notebooks/eda.py`（marimo）が
同じ関数を呼んで描くだけ。数値ロジックと結論を notebook に書かない（結論は調査単位の results/ の YAML）。

## 手順
1. 調査は `kind: investigation` の作業単位を作る（`work/…/INV-xxxx-<短い説明>.md` かフォルダ）。結論は results/ に
   YAML で残す（investigation は verified_by 不要・完了＝結論の記録）。
2. `uv run data list` でテーブルを選び、`uv run data profile <table_id> [--target <列> --task classification|regression]`。
   出力の YAML（列の欠損・型・一意数／数値統計／カテゴリ最頻／重複行数／目的変数の分布）を読む。
   **目的変数を確認せずに学習へ進まない**（不均衡・外れ値をここで掴む）。
3. train/test があれば `uv run data compare <train_id> <test_id> [--auc]`（統計量差・カテゴリの共通/固有・PSI／
   `--auc` で分布差 AUC＝adversarial validation）。PSI 目安：0.1 未満=安定・0.25 以上=大きな変化（門番でなく目安）。
4. `--auc` が目安 0.7 以上なら分布シフトの疑い。原因列を `analysis.cv_permutation_importance` で特定し、
   除外・変換の仮説を experiment スキルへ渡す。※ cv_permutation_importance は T-0027 で追加。
5. **人が見る・見せるとき**は `notebooks/eda.py` を調査フォルダへコピーし、
   `uv run marimo edit <コピー>`（対話探索）か `uv run marimo run <コピー>`（閲覧）。テーブルは環境変数で指定：
   `HARNESS_EDA_TRAIN`（表ID）／`HARNESS_EDA_TEST`（比較用・空可）／`HARNESS_EDA_TARGET`（目的変数・空可）。
   ビューは `harness.ds.eda` の**同じ関数**を呼ぶだけ（正本とズレない）。

## してはいけないこと
- train/test を結合して統計量を計算しない（リーク。compare/psi は2表を別々に集計する API になっている）。
- 目的変数の分布を確認せずにモデリングへ進まない。
- 図・notebook をレポートの正本にしない（正本は YAML。図は marimo 内の表示か results/ 置きの副産物）。
- 生 CSV を直接読み込むコードを書かない（データは store＝検証済みテーブルを通す）。
