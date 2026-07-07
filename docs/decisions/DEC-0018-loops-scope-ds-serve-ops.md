---
id: DEC-0018
status: accepted
date: 2026-07-07
---
# DEC-0018 loops 語彙の適用範囲——ds は fan-out+filter・serve は loop でない・ops retrain は記述のみ

## 状況（何を決める必要があったか）
DEC-0017 は loops（trigger×stop×policy）を運用モデルの語彙として正本化し、写像表で ds の実験 sweep を
「`StopCondition` の 2 個目の消費候補」と名指ししていた（DEC-0012 の「消費が実際に要ったとき一般化する」
の判断点）。T-0099 でこの候補をコードの事実に照らして検証する必要があった：`ds/experiment.py::run_experiment`
の実装は 1 変種を 1 回 CV 評価して `ExperimentResult(passed=passes(...))` を返して終わる関数であり、
反復・サイクルは存在しない。変種の並びは人が config で宣言する fan-out（experiment スキル）で、`passes` は
各変種への合否ラベル（フィルタ）である。あわせて serve（1 呼び 1 応答の配信）・ops retrain（EP-21 の CT 雛形）
についても loops 語彙の当てはめ方を判断する必要があった。

## 検討した選択肢
- A：DEC-0017 の名指しどおり、ds sweep を `StopCondition` の 2 個目の消費として扱い、`output: str` 固定を
  外して一般化する（sweep の反復探索を stop condition で表現できるようにする）。
- B：ds sweep は loop でなく fan-out＋filter と認定し、`StopCondition` は当面 agent 専用のまま広げない。
  serve は「適用しない」判断を正本化し、ops retrain は実コード化せず記述（写像）のみに留める。

## 決定と理由
**B を採用**。
- **ds**：`run_experiment` に反復・サイクルが実在しない以上、「2 個目の消費」は存在しない。`passes` は
  loop の停止条件ではなく変種ごとの合否ラベル（フィルタ）であり、変種の並びは loop の trigger でなく
  人が config で宣言する fan-out である。実在しない消費のために `StopCondition` を広げるのは早すぎる一般化
  （DEC-0012 の判断点で No＝一般的・再発する形が見えていない）。sklearn `*SearchCV`／optuna で足りない反復
  制御が実案件で要る、という形で消費が実在して初めて再判断する（DEC-0006：再発明しない＝探索は
  SearchCV/optuna が第一候補）。
- **serve**：`/predict`・`/invoke` はリクエスト駆動（1 呼び 1 応答のレイテンシ契約）で、「停止条件が満たされる
  まで作業サイクルを繰り返す」loop の定義（DEC-0017）に当てはまらない。応答経路に評価器ゲートを挟むのは
  配信の関心（レイテンシ・可用性）と衝突する。**適用しない、という判断自体を写像表と docs/serve.md に残す**
  （無理に統一しない）。serve を回す loop は serve の外側（予測 JSONL→`data monitor`→retrain の ops 周回）
  にある。
- **ops retrain**：`templates/ci/.github/workflows/retrain.yml` は time（cron）＋`workflow_dispatch` trigger ×
  `promote_model`（絶対 thresholds＋相対 champion 越え）関門 stop × ワークフロー YAML policy、という
  time+goal 合成の概念には当てはまるが、これは**記述（位置づけ）であって実コードの `StopCondition` 消費では
  ない**。実コード化（ops の閉ループが `loops.py` の語彙を実際に import して使うか）は T-0120 の判断に委ねる。
- いずれの場合も、`StopCondition` を広げる判断が要るときは `output: str` を直接広げず、**数値メトリクス用の
  別 Protocol を core に足す**方向を第一候補にする（agent の `GoalGate`・既存消費者を壊さない）。

## 再判断のトリガ条件（再判断すべき条件のみ・恒久停止ではない）
1. sklearn `*SearchCV`／optuna で吸収できない反復制御が実案件で要ると判断されたとき。
2. T-0120 で ops 閉ループが実コードの `StopCondition` 消費を要すると判断されたとき。

どちらの場合も、まず `output: str` を広げず数値メトリクス用の別 Protocol を core に足す案を検討する
（`GoalGate` を触らない）。

## 影響（良い点・悪い点・これからやること）
- 良い点：DEC-0017 が名指した候補を放置せず、コードの事実で検証して結論を確定できた（自己申告でなく検証で
  判断を閉じる、という AGENTS 第一原則の docs 版）。`StopCondition` は早すぎる一般化を避けたまま（DEC-0012）
  agent 専用に留まり、番人テスト（`tests/test_loops.py`）がシグネチャの拡大を機械的に止める。
- 悪い点：写像表に「適用しない」という否定形の判断が残り、読み手が「まだ手つかず」と誤読しうる →
  緩和：`docs/serve.md`・`docs/ops.md`・EP-23 item.md 写像表に理由つきで明記し、本 DEC への導線を張る。
- これからやること：T-0120（ops 閉ループの実コード化・EP-21 着地後）で上記トリガ (2) を判断する。関連
  [[DEC-0004]] [[DEC-0006]] [[DEC-0012]] [[DEC-0017]]。
