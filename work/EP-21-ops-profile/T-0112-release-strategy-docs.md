---
id: T-0112
kind: task
status: done
title: リリース戦略の文書化＝templates/serve README に Blue-Green・Canary 節（既存資産の使い方の明文化）
created: 2026-07-07
depends_on: [T-0111]
verified_by: [tests/test_release_docs.py::test_readme_has_bluegreen_and_canary_sections]
---
# T-0112 リリース戦略の文書化

## 狙い
コードもテンプレ実体も**増やさず**、既存資産（`templates/serve/` の k8s deployment＝image tag・replicas、
manifest＋指紋＝promote/rollback の来歴）の**使い方を明文化**する。Blue-Green（image tag 切替＝即ロールバック）
と Canary（replica 比率）は新しい仕組みでなく「既に持っている物の運用手順」なので、担保は文書＋節見出しの
構造検査だけでよい（item.md の取り込み判断）。

## 受け入れ基準
- **`templates/serve/README.md`** に節を追加（既存の節・記述は変更しない＝後方互換の追記のみ）：
  - **Blue-Green 節**：deployment の image tag を旧→新に切り替える手順・戻すときは tag を戻すだけ
    （ロールバック＝`promote_model` の champion 履歴と対応づけて来歴を残す）を、既存の
    `k8s/deployment.yaml` の該当キー名を引用して書く（引用するキーは実在するもの＝腐りの防止）。
  - **Canary 節**：新旧 2 つの Deployment を同じ Service selector に載せ replicas 比率で流量を分ける手順。
    「実トラフィックの出し分け＋外部指標収集（A/B）は配信基盤の関心＝やらない」の境界も 1 行明記。
- **`docs/ops.md`** のリリース戦略節から `templates/serve/README.md` の該当節へリンク
  （doclint の `templates/` 参照実在検査に通る形で）。
- 新規ファイル・新 CLI・コード変更は**無し**（.md の追記と検査テストのみ）。

## 触ってよいファイル
`templates/serve/README.md`（節の追記のみ）・`docs/ops.md`（追記）・`tests/test_release_docs.py`（新規）。
`templates/serve/` の yml/Dockerfile・src/ は一切変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_release_docs.py::test_readme_has_bluegreen_and_canary_sections`（**unit**）：
  `templates/serve/README.md` に Blue-Green・Canary の節見出しが在る（見出し文字列は受け入れ基準の構成
  から導く）。
- `test_release_docs.py::test_readme_cites_existing_k8s_keys`（**unit**）：README の Blue-Green/Canary 節が
  引用する k8s キー（例 `image:`・`replicas:`）が `templates/serve/k8s/deployment.yaml` に実在する
  （文書とテンプレの参照整合＝deploy_lint の思想を文書側にも適用）。
- `uv run verify` 全体緑（doclint・deploy_lint が README 変更後も通ること）。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：手順が既存資産だけで実行可能か＝新しい部品を暗黙に前提にしていないか／
A/B との境界（やらないこと）が明記されているか／deployment.yaml のキー名引用が正しいか）
