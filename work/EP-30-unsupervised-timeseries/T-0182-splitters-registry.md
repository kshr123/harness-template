---
id: T-0182
kind: task
status: todo
title: 時系列の分割を足すときに SPLITTERS レジストリへ移す（消費者と同時に作る）
created: 2026-07-10
depends_on: []
verified_by: []
---
# T-0182 分割器を config から選べるようにする（time_series の実需要と同時に）

## 何が問題か
`src/harness/ds/cv.py` の `make_folds` は、分割器を `stratify_by` / `group_by` の有無から if/elif で
選んでいる（KFold・StratifiedKFold・GroupKFold・StratifiedGroupKFold）。config が kind 文字列で選べる
軸になっていない。purged / embargo つきの時系列分割や `RepeatedStratifiedKFold` を足す口が無い。

## 独立レビューによる訂正（2026-07-10）
このタスクは当初 EP-27 にあり、根拠を 2 つ挙げていた。どちらも実測で崩れたので書き直した。

1. **「分割器だけが唯一、拡張口の無い軸」は偽**。反例が 2 つ実在する。`pipeline.py` の
   `cluster_label` / `anomaly_score` エンコーダは KMeans / IsolationForest を直書きしていて手法の軸が無い
   （EP-30 の item.md 自身がこれを認めている）。また `run_experiment` は `group_by` を受け取らないので、
   GroupKFold は実験の正規経路から到達できなかった（→ 実害が大きいので T-0186 として先に塞ぐ）。
2. **fold 割当を長表（`(fold, role, id)`）へ移す提案は時期尚早**。purged / repeated という消費者が
   まだ居ない。「計画は近い作業だけ先に詳しくする」に反するので、この提案は落とす。長表が要るのは
   purged / embargo を実装するときで、そのときに同じタスクで移す。

なお現行の「データの性質（stratify / group / order）を宣言すると正しい分割器が導出される」設計は、
kind 文字列より優れている面がある：group のあるデータに `kind: kfold` と書いてリークさせる、という
誤設定を構造的に防いでいる。**レジストリ化は、この安全性を失わない形でしか行わない。**

## だから EP-30 に置く
`time_series` という本物の消費者が来て初めて、分割器を選ぶ軸に意味が出る。`make_time_folds` と
`order_by` で拡大窓（expanding window）は既にあるので、足りないのは purged / embargo だけである。

## 何をするか（着手時に詳しくする。今は outline）
- `SPLITTERS: Registry[Entry]`（`uv run data splitters`）。kind は sklearn のクラス名の写しなので
  `require_source` は不要（名前は既に外にある）。
- 誤設定リークを防ぐ性質は残す：`group_by` が指定されているのに group を跨ぐ分割器を選んだら
  `ValueError` で止める（黙ってリークさせない）。
- purged / embargo を足すときに、fold 割当の正本を長表へ移す（このときは挙動が増えるので、
  移行と機能追加を別コミットに分ける）。

## 受け入れ基準（着手時に確定させる）
- 同じ `(df, kind, seed)` なら必ず同じ割当（決定性）。`seed` は明示引数。
- 期待値は入力の構成から導く：valid の和集合が全 id と一致・valid どうしは互いに素・
  `group` では同じグループが train と valid に跨がらない。
- `uv run verify` 全成功。
