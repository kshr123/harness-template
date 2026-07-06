---
id: EP-17
kind: epic
status: done
title: 配信プロファイル（serving profile＝可搬 ONNX・sync 配信・release/monitoring テンプレートを今用意する）
plan: detailed
requirements: [REQ-002]
depends_on: [EP-15, EP-16]
created: 2026-07-06
closed: 2026-07-06
---
# EP-17 配信プロファイル（serving profile・Wave 5）

## 目的
参考リポ `ml-system-in-actions`（機械学習システムデザインパターン）の核＝「学習した champion が**その後どう配信・監視されるか**」
という**配信境界**を、当リポの流儀（ローカル完結・config・registry・構造化表・プロファイル境界＝DEC-0004）に翻案して今用意する
（DEC-0010「今できる理想形を作る」）。Docker/K8s/FastAPI は重要な資産なので、**テンプレート＋構造 lint（verify で回る）**として
同梱し、実行基盤（クラウド）は利用者環境に委ねる。中核・ds プロファイルは一切壊さない（新規 `harness.serve` プロファイルに閉じる）。

## 参考リポからの取り込み判断（翻案・不採用を明記）
- **ONNX 可搬アーティファクト**（本の中心＝batch/cache/load-test/A-B すべて ONNX で配信）→ `FORMATS["onnx"]`（optional extra）。
  当リポの Pipeline は polars 特徴＋sklearn の混成なので **`to_numpy` 以降の sklearn 部分**を ONNX 化（本も純数値で同じ構図）。
- **sync 配信**（web_single_pattern／FastAPI で champion を出す）→ `harness.serve`（FastAPI app＋`serve` CLI）。registry の
  champion を読み `/predict`・`/health`・`/metadata`。予測は来歴付き JSONL に記録（prediction_log パターンの翻案）。
- **release patterns**（model-in-image／model-load）→ `templates/serve/`（Dockerfile.serve・docker-compose・k8s manifests）。
  実体は「利用者がコピーして使うテンプレート」。当リポは**構造 lint**（deploy_lint）で参照整合を verify で守る。
- **prediction monitoring**（配信の分布ドリフト監視）→ `data monitor`（既存 eda.psi/drift_auc を配信ログ×学習基準に適用）。
- **この EP では未着手（対象外ではない・順序の問題＝[[DEC-0014]]）**：prediction cache・edge・circuit breaker・load test・
  online/shadow A-B ルーティング・async キュー・gRPC・クラウド固有（S3/GCS）。実行時ルーティング/耐障害は将来のプロファイル
  （ops 系）で順次作る。model_db（関係 DB のレジストリ）は当リポが file manifest＋指紋で代替済みなので作らない（重複回避）。
  cifar10（DL・torch 前提）はサンプル題材なので取り込まない。

## 進め方（各タスク＝1 PR・テスト先書き・独立レビュー（maker≠checker）・verify 緑で done）
範囲の線引きは [[DEC-0013]]。土台（onnx/serve extras・serve script・mypy overrides）は導入済み（b1b8b19）。
- **T-0084 ONNX 保存形式**（`ds/onnx_format.py`＋`ds/models.py` の FORMATS に条件登録・`data formats` カタログ）。可搬アーティファクトの土台。
- **T-0085 serving プロファイル**（新 `src/harness/serve/`＝FastAPI app＋`serve` CLI＋予測 JSONL ログ＋`PROFILE`・`serve` スキル＋docs/serve.md）。
- **T-0086 配信テンプレート＋deploy_lint**（`templates/serve/`＝Dockerfile/compose/k8s＋`serve/deploy_lint.py` を `PROFILE` に配線＋doclint に `templates/`＋自リポ config に harness.serve）。
- **T-0087 data monitor**（`ds/monitor.py`＋`ds/cli.py`＝配信ログ×学習基準の psi/drift 監視表）。

## 依存順
T-0084（ONNX）と T-0087（monitor）は独立。T-0085（serve パッケージ）→ T-0086（テンプレ＋lint は serve/__init__ の PROFILE を拡張）。

## この EP の範囲外（＝将来のプロファイルで順次作る・対象外ではない）
実時間の A-B ルーティング・circuit breaker・load test・async キュー・gRPC・クラウド固有（S3/GCS 実装）・torch/DL。
これらは本ハーネスの**対象**だが、この EP では未着手（順序の問題）。ハーネスは学習“から”始めるだけで学習に限らない
＝[[DEC-0014]]。実行時基盤は利用者環境に委ね、ハーネス側は抽象＋テンプレ＋構造 lint＋スキルで担保する（DEC-0013 の思想）。
