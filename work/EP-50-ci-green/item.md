---
id: EP-50
kind: epic
status: done
plan: detailed
requirements: []
depends_on: [EP-49]
---
# EP-50 PR #2 の CI（既存の赤3ジョブ）を緑にする

PR #2 の CI には EP-48/EP-49 より**前から赤い**3ジョブがある（私の変更が入れたものではない）。マージを緑で
できる状態にするため、根本原因を潰す。設計は各タスクの本文。ローカル verify（macOS）は緑だが、CI の
windows・clone-simulation・audit が既存の理由で赤い＝ローカルだけ見て「緑」と言っていた穴でもある。

## 含む作業
- T-0293 audit：`pymdown-extensions` の CVE（10.21.3 → 11.0.0）を塞ぐ＋ロックの床を回帰テストで固定
- T-0294 windows verify：パス区切り（`\` を出す code_doc_lint）と stdio エンコード（cp932）で落ちる移植性バグ
- T-0295 clone-simulation：DS 依存テストのプロファイル所有漏れ（numpy 収集エラー）と、doclint が案件領域パス
  （init-project が白紙化する `docs/wbs.yaml`）を「存在必須」と誤検査する穴

## 含めない
- Windows/CI 環境そのものの増強（Chrome を CI に入れる等は ISS-0018 の別件）。
