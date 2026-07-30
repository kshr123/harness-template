---
id: T-0293
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-49]
verified_by:
  - tests/test_guardrails.py::test_audit_exemptions_require_reason
---
# T-0293 audit を緑に（pymdown-extensions の CVE）
`pip-audit` が `pymdown-extensions 10.21.3`（CVE-2026-61632・fix 11.0.0）を検出して CI の audit が赤い。
まず版上げを試したが、**marimo（EDA スキルの notebook 開発ツール）の全リリースが `pymdown-extensions<11` を
固定**しており、床>=11 を宣言すると `uv lock` が解決不能になるのを実測した＝fix 版を今は採れない。
そこでリポジトリ既定の作法（理由必須の allowlist）に従い、`.pip-audit-ignore` に CVE を**理由＋見直し期限つき**で
載せて塞ぐ（ignore で目をつぶるのでなく、修正版が依存側に無い間の正式な扱い）。markdown 拡張の脆弱性で、
当リポに信頼できない markdown を通す経路は無い（dev/notebook 用途のみ）。marimo が >=11 を許す版を出したら外す。

## 受け入れ基準
- [x] `.pip-audit-ignore` に CVE-2026-61632 を理由＋見直し期限（2026-10）つきで載せた。
- [x] `pip-audit`（ローカル・全部入り・ignore 適用）が既知脆弱性ゼロ（1 ignored）。
- [x] 免除に理由が付いていることを検査するテストが緑（理由の無い免除は fail）。
