---
id: EP-39
kind: epic
status: done
plan: detailed
created: 2026-07-20
closed: 2026-07-20
requirements: []
depends_on: []
---
# EP-39 段階レビュー（思想→コード）の勧告を実装し、理想へ寄せる

fable による6層の段階レビュー（思想→論理→物理→コード→検証網→文書）を敵対的検証つきで実施し、
churn・思想違反を除いた上位勧告を採用した。抽象→具体の貫通で破れていた2リンク（コード→文書、思想→複製境界）と、
検証土台に残った fail-open を閉じるのが主眼。各改善は maker≠checker（別 fable）で確認し、`uv run verify` 緑を保つ。

## 採用した勧告（rank 順）
- **T-0233**（rank1）：`checks.toml` 不存在を ValueError に。verify 土台の最後の fail-open を閉じる（条件1）。
- **T-0234**（rank2）：プロファイル集合・所有区分・docs 索引の導出点を1つにする。stats 陳腐化クラスタの根治。
- **T-0235**（rank3）：思想の中核判断を複製で消えない正本へ移し、L-ID 根拠参照を撤去（条件4の自己裏切り解消）。
- **T-0236**（rank4）：`/health` に champion 記録突合→不一致で stale＋503。切り戻しを配信の実体まで届かせる。
- **T-0237**（rank5）：branch protection / required checks 化の手順を docs へ記載（宣言された唯一の不動点への到達路）。
- **T-0238**（rank6）：retrain 雛形の continue-on-error 助言を削除し、却下（緑）と故障（赤）を exit code で分離。
- **T-0239**（rank7）：promotion 記録の書き込み口を追記専用に（刻み検証＋既存上書き拒否）。

## 却下（fable が churn/観測事故なしで棄却）
条件1×3の優先順位明文化 / 検査表の出所列 / directions・passes の中核昇格 / 裸 T-ID 一掃。
