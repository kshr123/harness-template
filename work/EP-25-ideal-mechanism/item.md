---
id: EP-25
kind: epic
status: in-progress
plan: detailed
requirements: [REQ-001]
depends_on: [EP-23]
created: 2026-07-07
---
# EP-25 理想の仕組みへの進化（自己整合・検査委譲・資産境界・レビュー比例化・メタ整合）

## 目的
このハーネスの「理想」＝**自分自身に課したルールを、自分自身が機械的に満たしている状態**。核（verify-gate・
work 木＋pm.lint・goal-gate/judge/exit-1・maker≠checker・fail-closed・進化ラチェット・意味論 lint）は世界水準の
資産として温存し、その周囲を核と同じ規律で整え、**縮小でなく進化**させる（オーナー意思：今考えうる理想を作り、
今後も拡張・進化させる。抜本的変更も厭わない）。

神の視点レビュー6件（fable ×6・Opus 統合）が掘り当てた「方向を捨てても残る具体改善」を材料にする。到達目標：
1. 語彙・抽象は**実消費者が存在するものだけが core に住む**（DEC-0012 の規律をコード配置が体現）。
2. 検査は**プロジェクト固有意味論だけを自前**で持ち、汎用形式検査は既製バリデータへ委譲（DEC-0006/0008 を lint 群自身へ適用）。
3. **複製で残る資産（templates/）と消える領域（work/）の境界が正しく**、templates 配下の全資産に腐敗防止検査のオーナーが機械対応。
4. **レビューのコストが差分のリスクに機械的に比例**（独立性は全 tier で不変・深度だけ比例）。
5. **メタ層が自らの「正本一元・棚卸し」ルールを守り**、違反を機械が RED にする。

## タスク（歩く骨組み→差し替え）
- **T-0133**（A・骨組み）loops の正直化：`loops.py`→`agent/goal.py` へ畳み込み・死んだ `Trigger` 削除・墓標テスト・DEC-0020。
- **T-0134**（C-1・骨組み）検査委譲の関門 DEC-0021＋actionlint/check-jsonschema を pre-commit 配線（vacuous pass を実測で潰す）。
- **T-0135**（C-2・差し替え）自前 lint の汎用層剥離＋「停止」日本語 grep→言語非依存 `# stop:` マーカーへ。
- **T-0140**（D-1・差し替え）実験正本雛形を `templates/experiment/` へ移設・e2e/スキル追従・template-copy.md を doclint 走査対象へ。
- **T-0137**（D-2・抜本1）templates 資産のオーナー検査ラチェット（資産を足したら検査オーナーも足す＝verify 強制）。**機械検査で実施**（コードの構造不変条件＝機械化の射程内）。
- **T-0138**（B・改訂）レビューのリスク比例化（diff で full/light 判定）を **review スキル＋DoD に規約として明文化**（新 pm 検査は足さない）。**理由**：EP-24 rollback で「文書構造の機械化（lede 必須等）は撤去・規約へ」と決まった。「レビュー節必須」の pm 検査は同型（文書構造の機械化）＝規約に留める。レビュー深度の判定基準（src/tests/templates に触れる＝full）を skill に書き、独立性は全 tier で不変。
- **T-0139**（E・改訂）メタの自己整合：正本一元の実施（同趣旨の重複を 1 か所へ）・learnings 棚卸しを **手作業で実施**。**規範文の重複検出器（doc_standards 型）は新設しない**（rollback＝「文書規律は機械検査でなく規約」と整合。doc_standards は撤去済み）。

**機械化の射程（owner 決定 2026-07-07・rollback 整合）**：真に機械化できる構造/コード不変条件だけ機械検査（T-0137・actionlint 等）、文書/プロセス/散文品質の規律は〈私への規約〉（skill/AGENTS）に留める（T-0138/0139）。

## EP-24 競合回避
別ターミナルが worktree で EP-24（docs 人間可読化・T-0130 コミット済み／T-0131・T-0132 todo）稼働中。
- 競合ゼロで即可：T-0134・T-0135・T-0137（コード・テスト・pre-commit・新 DEC のみ）。
- 軽微競合・即可（先に main へ入れ EP-24 が rebase）：T-0133（AGENTS 2 行）・T-0140（experiment スキル 1 行・template-copy.md 最小修正）。
- EP-24 着地後：T-0138（review スキル・DoD は T-0132 の改稿対象）・T-0139（AGENTS/method/learnings は T-0132 の改稿対象・doc_standards.py は EP-24 の新資産）。

## 原則
各タスクは「効かせる guard を先に RED で書いてから直す」（method.md C 節・検査先行）。設計＝fable／実装＝sonnet／
独立レビュー＝Opus（別モデル・ミューテーションで guard の RED を実測）。done は verified_by に受け入れ基準を確かめる
テストの場所を明記（空・指す先無しは pm 検査で失敗）。
