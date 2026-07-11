---
id: EP-32
kind: epic
status: done
plan: detailed
requirements: [REQ-001]
depends_on: []
created: 2026-07-10
---
# EP-32 今日踏める穴を塞ぐ（黙って通ってしまう経路）

## 何が問題か（すべて実測で再現済み・2026-07-10）
「完了を自己申告できない」「品質を黙って落とせない」という保証が、**悪意なく普通に作業した結果**で無効化される。

### 1. goal.yaml に `thresholds:` を書き忘れると、どんな出力でも合格する【最重要】
`uv run agent run --spec … --goal goal.yaml` は一次 CLI 経路。`goal_from_mapping` が `thresholds` を
黙って `{}` に補い（`agent/goal.py:203`）、`passes(scores, {})` は判定 0 件なので True。
**でたらめな出力が cycle 1 で `goal_met`・exit 0。**

守られたファイルへの差分ゼロ、悪意ゼロ、書き忘れ 1 行で、基盤の看板保証が無音で消える。
CLI の `--goal-expected` 側は省略時に `{"exact_match": 1.0}` へ倒しているのに、YAML 側だけ `{}` に倒れる。
**この非対称そのものが見落としの証拠。**

### 2. マーカーの綴り違いで 887 テストが全部消え、しかも合格になる
`checks.toml` の `-m 'unit and not slow'` を `unitt` と書き間違えると、pytest は「該当 0 件」の exit 5 を返し、
`checks.py` はそれを合格として扱う（`checks.py:103`）。**そして番人テスト自身が `unit` マーカー付き**
（`tests/test_verification_mechanism.py:18` の `pytestmark`）なので、その typo が起きたときに限って
自分も deselect され、走らない。門番が門の内側に住んでいる。

マーカーの改名リファクタや複製先の調整で、**普通に踏む**。

### 3. 初回昇格は「有限でありさえすれば」何でも champion にする
`promote_model` / `promote_agent` は thresholds が空でも `change_threshold(primary)` を必ず足すので、
判定 0 件には到達しない。しかし比較対象の無い初回昇格では改善量を問えないので、**発散していなければ通る**。
これは docstring に明記された設計であり隠れた欠陥ではないが、**黙示の緩和**であることに変わりはない。
serve はその champion を配信する。

### 4. 「判定していない」と「合格」が同じ値で表される
`passes(x, {})` が True を返すのは意図された仕様（`tests/test_ds_eval.py` が固定）で、
「まず回して指標を見る」探索は正当な使い方。**だから `evaluate` を一律 ValueError にしてはいけない**
（ds の探索経路が全滅する）。正しいのは「判定 0 件」を合格と**区別できる型**にすること。
`evaluate_holdout` は既に正解を持っている（thresholds 無し → `passed=None`）。

## 却下した対策（L-017・L-019 の適用記録）
- **`gates.evaluate` の空 specs を一律 ValueError**：探索の正当な経路を壊す。発生源は `goal_from_mapping` の側。
- **`thresholds` と `metrics` の集合等式を強制**：二値の既定 metrics は 11 個あり、`brier`・`calibration_gap`・
  `mcc` は観測目的で測る。全部に閾値を強制すると `brier: 1.0` のような**形だけの閾値**を人が書く。
  構成から導けない数値を機構が量産する（L-019 が禁じた形）＝空より悪い。
- **pytest exit 5 の廃止**：複製先は DS のテストを正当に消すので、層が正当に空になる。
  「tests/ が空でない限り失敗」は複製先にダミーテストを書かせる（L-017 の逆流）。
  マーカーの不変条件だけで typo 経路は閉じるので、exit 5 は残す。

## 検査の置き場についての原則（新しく分かったこと）
リポジトリの中に**不動点は存在しない**。`checks.py` を編集する手は `checks.toml` を編集する手と同じ。
後退が止まるのは (1) 差分の独立レビュー、(2) 作業ツリーの外（GitHub の branch protection・required checks）だけ。

したがって **リポ内の全検査は「事故防止」であって「改竄防止」ではない**。改竄防止を名乗れるのはリポ外の層だけ。
この区別を AGENTS に書く（T-0189 と同じタスクで）。

## タスク
| ID | 何を | 順 |
| --- | --- | --- |
| T-0197 | `goal_from_mapping` の `thresholds` を非空必須にする（1 関数・数行） | 1 |
| T-0198 | `checks.toml` の `-m` 式の不変条件を `run_check` 冒頭で検査し、満たさなければ起動を拒否する | 2 |
| T-0199 | 「判定 0 件」を合格と区別する（`passed: bool \| None`）。初回昇格の緩和を明示引数にする | 3 |
