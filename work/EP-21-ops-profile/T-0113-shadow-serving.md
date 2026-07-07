---
id: T-0113
kind: task
status: todo
title: shadow 配信＝/predict の 1 プロセス内分岐・PREDICTION_LOG_FIELDS に role を後方互換追加
created: 2026-07-07
depends_on: [T-0112]
verified_by: [tests/test_serve_shadow.py::test_predict_logs_primary_and_shadow_roles]
---
# T-0113 shadow 配信（app/runtime/docs 契約）

## 狙い
`/predict` で champion（primary）の予測を返しつつ、shadow 版モデルでも**同じ入力**を算出して JSONL に
`role: primary|shadow` で記録する。応答は primary のみ（呼び手の契約は不変）＝**1 プロセス内の分岐**に
閉じ、実行時基盤（トラフィック分割・サイドカー等）に踏み込まない唯一級の release パターン。
serve は**後方互換拡張のみ**（既存の応答スキーマ・既存ログ読者を壊さない）。

## 受け入れ基準
- **`serve/runtime.py`**：`PREDICTION_LOG_FIELDS` に `role`（`"primary" | "shadow"` の str）を**後方互換で追加**
  （既存キーの改名・削除・型変更は禁止。キー完全一致検査（build_log_entry のドリフト検知）は新契約に更新）。
  shadow 行は primary 行と同じ `input_fingerprint` を持つ（同一入力の突き合わせ＝monitor がそのまま使える）。
- **`serve/app.py`**：shadow モデルは**任意**（環境変数 例 `SERVE_SHADOW_NAME` が未設定なら従来どおり
  primary 行のみ＝既定の挙動は完全に不変）。設定時は `/predict` 1 リクエストで primary＋shadow の 2 行を
  JSONL に追記し、**HTTP 応答は primary の結果のみ**（応答スキーマ不変）。shadow の予測失敗は応答を
  落とさない（primary は返す・shadow 行にはエラーを記録 or 行を出さない方針を docs に明記）。
- **`/metadata`**：shadow が有効なとき shadow モデル名を含める（後方互換のキー追加のみ）。
- **導線（DEC-0009/DEC-0016）**：`docs/serve.md` の PREDICTION_LOG_FIELDS 契約表に `role` を追記・
  shadow の有効化手順（env）を記載。`.claude/skills/serve/SKILL.md` に shadow の 1〜2 行導線。
  `docs/ops.md` の shadow 節から docs/serve.md へリンク。
- 新 CLI コマンドは足さない（有効化は env のみ）。core・ds は変更しない。ops モジュールも変更しない
  （このタスクは serve の後方互換拡張＝EP-21 で唯一 serve に触るタスク）。

## 触ってよいファイル
`src/harness/serve/{app.py,runtime.py}`（後方互換拡張のみ）・`docs/{serve.md,ops.md}`（追記）・
`.claude/skills/serve/SKILL.md`（導線 1〜2 行）・`tests/test_serve_shadow.py`（新規）・
既存 serve テスト（契約表更新に伴う**最小限**の期待値追従のみ・検査を緩めない）。
templates/・ds/・core・agent は変更しない。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_serve_shadow.py::test_predict_logs_primary_and_shadow_roles`（**integration**）：shadow を設定して
  `/predict` を 1 回→JSONL がちょうど 2 行・role が {primary, shadow}・両行の `input_fingerprint` が一致・
  応答 body は primary の値のみ（期待値は仕込んだ 2 モデルの構成から導出）。
- `test_serve_shadow.py::test_no_shadow_env_behaves_as_before`（**integration**）：env 未設定で 1 行のみ・
  role は `primary`・応答スキーマは従来と同一（後方互換の実証）。
- `test_serve_shadow.py::test_shadow_failure_does_not_break_response`（**unit**）：shadow の predict が例外でも
  HTTP 200・primary の結果が返る。
- 既存の serve e2e・deploy_lint が緑のまま（壊していない証拠）。`uv run verify` 全体緑。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：既存ログ読者（data monitor・read_prediction_logs）が role 追加後も壊れないか実測／
応答スキーマが 1 バイトも変わっていないか／shadow 無効時の経路にオーバーヘッド・分岐漏れが無いか）
