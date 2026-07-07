---
id: EP-21
kind: epic
status: todo
title: 運用プロファイル harness.ops（CI/継続学習/リリース戦略/shadow/監視の閉ループ）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-17, EP-19]
created: 2026-07-06
---
# EP-21 運用プロファイル（harness.ops）

## 目的（DEC-0014 の続き＝学習の後工程を対象に含める）
DEC-0014 で「ハーネスの対象は ML ライフサイクル全体」と正本化した。EP-17 で配信（serve）まで来たが、その先＝
**CI（verify ゲート）・継続学習（CT）・リリース戦略・監視の閉ループ**が未着手。実行時の重い基盤（GitHub ランナー・k8s・
クラウド）は利用者環境に委ね、ハーネスは**テンプレート＋構造 lint＋プロファイル境界＋スキルの導線**で担保する
（deploy_lint と同じ思想）。中核・ds・serve は壊さない（新規 `harness.ops` プロファイルに閉じる）。

## 取り込み判断（serving/ops 調査・now 層）
既に代替済みで作らないもの（重複回避）：model registry＝`promote_model`/`champion`/manifest＋指紋・batch 推論＝`data predict`・
release テンプレ＝`templates/serve/`・drift 監視＝`data monitor`・可搬形式＝ONNX・課題/アラート先＝issues backend・
オフライン特徴量＝docs/data 正本＋Storage 抽象。**この上の「配信後〜運用」の輪**に絞る：
- **CI verify テンプレ**：`templates/ci/.github/workflows/verify.yml`（利用者の複製先が PR→verify のゲートを持てる雛形）＋
  `ops/ci_lint.py`（実行しない・構造検査＝verify step の有無・Python 版・extras。deploy_lint と同型）。※自リポの CI は既にある。
- **継続学習（CT）雛形**：`retrain.yml`（schedule→experiment→`data monitor`→閾値を満たせば promote）。既存部品の結線のみ。
- **shadow 配信**：`serve/app.py` に `/predict` で champion を返しつつ shadow 版も算出し `role: primary|shadow` で JSONL 記録
  （`PREDICTION_LOG_FIELDS` の後方互換拡張＝docs/serve.md も更新）。1 プロセス内の分岐＝実行時基盤に当たらない唯一級の release パターン。
- **監視→課題起票の閉ループ**：`data monitor --file-issue`（band が PSI_ALERT 超で issues に冪等起票。門番にしない思想は維持＝
  exit 0・起票は副作用）。既存 2 部品（monitor・issues）の合成。
- **リリース戦略の文書化**：`templates/serve/README.md` に Blue-Green（image tag 切替＝ロールバック）・Canary（replica 比率）節
  （コードもテンプレ実体も増やさず既存資産の使い方を明文化）。

## やらないこと（later・YAGNI・適用対象が今は無い）
S3/GCS 実装（`storage.resolve_uri` に差し替え口は用意済み・実需要が出るまで待つ）・retry/timeout/circuit breaker（serve に外部呼び出しが
無い＝呼ばれない防御コードになる）・オンライン特徴量ストア（`/predict` は呼び手が特徴を渡す契約＝競合）・A/B（実トラフィック出し分け＋
外部指標収集＝配信基盤の関心）・streaming（Kafka 等＝実行時の重い基盤）・prediction cache（下地=input_fingerprint はあるが実測で
問題化してから）・gRPC（REST で十分・必要時に非破壊で並行追加）。いずれも DEC-0014 の対象内だが順序で後回し。

## 進め方（分解は着手直前に detailed 化）
T：`harness.ops` プロファイル骨組み（PROFILE 登録・空 ci_lint・config 1 行）→ T：CI verify テンプレ＋ci_lint → T：リリース戦略の
文書化 → T：shadow 配信（app/runtime/docs 契約）→ T：CT 雛形＋ci_lint 拡張 → T：`data monitor --file-issue`。歩く骨組み＝
プロファイル境界＋CI テンプレを先に一巡させ、各部を差し替え。

採番（detailed 化・2026-07-07）：
- T-0110 harness.ops 歩く骨組み＝PROFILE 登録・空 ci_lint・config 1 行・docs/ops.md の器
- T-0111 CI verify テンプレ（templates/ci の verify.yml）＋ci_lint 本実装（実行しない構造検査）
- T-0112 リリース戦略の文書化＝templates/serve README に Blue-Green・Canary 節
- T-0113 shadow 配信＝/predict の 1 プロセス内分岐・PREDICTION_LOG_FIELDS に role 後方互換追加
- T-0114 CT 雛形 retrain.yml＋ci_lint 拡張（既存部品の結線のみ）
- T-0115 data monitor --file-issue＝PSI_ALERT 超で issues に冪等起票（門番にしない・exit 0）
