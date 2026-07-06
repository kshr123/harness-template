---
id: DEC-0013
status: accepted
date: 2026-07-06
---
# DEC-0013 配信プロファイル（harness.serve）の範囲を決める

## 状況（何を決める必要があったか）
参考リポ `ml-system-in-actions`（機械学習システムデザインパターン）を取り込むにあたり、オーナーが「Docker/K8s/FastAPI も
重要なので現時点で用意できるものは用意する」と明示（DEC-0010 の延長）。ただし参考リポの大半は実行時サービング基盤
（配信ルーティング・耐障害・負荷試験）で、当リポの「ローカル完結の学習・実験・レジストリ」という核とは関心が違う。
何を配信プロファイルに入れ、何を将来に回すかの線引きを正本化する必要があった。

## 検討した選択肢
- A：参考リポを丸ごと移植（sync/async・cache・edge・circuit breaker・load test・A/B ルーティング・model_db）。
- B：**配信「境界」だけを翻案**＝「学習した champion がその後どう配信・監視されるか」を、当リポの流儀（ローカル完結・config・
  registry・構造化表・プロファイル境界）に落とす。実行時基盤（クラウド・ルーティング）は利用者環境に委ね、当リポは
  テンプレート＋構造 lint で「壊れないテンプレート」を配る。

## 決定と理由
**B を採用**。新規プロファイル `harness.serve` に閉じ、中核・ds を一切壊さない。入れるもの：
- **ONNX 可搬形式**（optional extra `onnx`）：FORMATS への条件登録（DEC-0006 の差し替え口）。polars+sklearn 混成 Pipeline の
  **`to_numpy` 以降の sklearn 尾部のみ**を変換（本も純数値で同じ構図）。ONNX は任意コード実行が無く skops より構造的に安全。
- **sync 配信**（extra `serve`）：FastAPI で champion を `/predict|/health|/metadata`。予測は来歴つき JSONL に記録
  （prediction_log パターンの翻案）。`serve` CLI＝uvicorn 起動。
- **release テンプレート**：`templates/serve/`（Dockerfile/compose/k8s）を「利用者がコピーする雛形」として同梱。実行はせず
  **deploy_lint**（参照整合の構造検査）を PROFILE に載せ verify で守る（DEC-0009 の「入口＝lint＋スキル」拡張）。
- **data monitor**：既存 eda.psi/drift_auc を配信ログ×学習基準に適用する監視表。

将来に回す（**対象外ではなく未着手の将来プロファイル＝順序の問題**。根拠は [[DEC-0014]]）：A/B・shadow ルーティング・
prediction cache・edge・circuit breaker・load test・async キュー・gRPC・クラウド固有（S3/GCS 実装）・model_db（関係 DB の
レジストリ＝当リポは file manifest＋指紋で代替）。※本行は当初「配信基盤側の関心＝学習ハーネスの外」と書いていたが、
その線引きは誤り（DEC-0014 で是正）。

**規約の昇格**（DEC-0012＝即昇格）：プロファイルのモジュール（`ds/__init__`・`serve/__init__`）は PROFILE の再 export だけを持ち
**重い依存を module top で import しない**（fastapi は app/cli 内で遅延 import）。`.harness/config.toml` の profiles に
`harness.serve` を足し、deploy_lint が出荷テンプレートを毎回 verify で検査する（「軽 import」をテストで固定）。

## 影響（良い点・悪い点・これからやること）
- 良い点：学習ハーネスから配信への橋（可搬アーティファクト・sync 配信・監視）が入口つきで揃う。Docker/K8s/FastAPI 資産を
  「壊れないテンプレート」として配れる。中核・ds は無傷（プロファイル境界）。
- 悪い点：verify の依存が増える（onnxruntime 等）。→ 緩和：extra に隔離（非配信案件は重さゼロ）・serve/onnx テストは
  integration/e2e マーカー・CI は分割せず `uv run verify` 一本を維持。
- これからやること：EP-17（T-0084 ONNX・T-0085 serve・T-0086 テンプレ＋lint・T-0087 monitor）。Windows×3.14 の onnxruntime
  wheel は T-0084 着手時に確認（無ければ extra を外す＝skip で誤魔化さない）。関連 [[DEC-0006]] [[DEC-0009]] [[DEC-0010]] [[DEC-0012]]。
