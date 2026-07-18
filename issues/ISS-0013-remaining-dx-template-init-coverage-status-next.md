---
id: ISS-0013
kind: question
state: resolved
found_in: EP-16
created: 2026-07-06
closed: 2026-07-18
promoted_to: T-0231
title: 残る DX（template-init・カバレッジ・ラチェット・status --next）は設計判断が要るので分離
---
> 解決（2026-07-18・T-0231 で判断を確定）：3 項目の判断を下した。status --next は着手＝実装済み
> （`uv run status --next`）。template-init は実験の識別子の設計が先＝次に実験を scaffold する時に一緒に決める。
> coverage ratchet は案件が育つ前は時期尚早＝床を決める根拠ができた時に足す。後者 2 つは消費者・動機が現れた
> 時に着手する（見送りの理由と再開条件は T-0231 に記録）。判断を委ねられたこの課題の役目は果たした。

# ISS-0013 残る DX の分離（template-init・coverage ratchet・status --next）

## 事象
Wave 4（EP-16）の中核＝正本ドリフト/規約の機械検査・実験 config の型付け・CLI スモーク・Windows CI は完了した。
残る 3 つの DX 項目は、単純な追加でなく**設計判断か新依存**を伴うため、本エピックから分離して owner 判断に委ねる。

## 分離した項目と理由
1. **template-init（複製の機械化＋複製後 verify）**：現状の雛形 train.py は `WORK_ID="E-0001"`・store の table_id（`e0001_*`）を
   ハードコードし「丸ごとコピーして config だけ書き換える」流儀。真の機械化には ID の書き換え（train.py の識別子・item.md の id・
   table 定義）が要り、**実験の識別子をどう持つか**（train.py をパラメタ化するか・per-experiment のままか）の設計が先。
   赤テスト（複製→--test スモーク緑）を書いてから設計 → 実装する。
2. **coverage ratchet（CI 別ジョブ）**：pytest-cov（新依存）＋カバレッジの baseline 保存＋CI での比較が要る。新規テンプレに
   カバレッジ床を課すのは時期尚早（テストは property/例示/CLI で十分厚い）。案件が育ってから floor を決めるのが素直。
3. **status --next**：`uv run status` に「次に着手すべき単位」を提案する枝。あると便利だが中核でなく、着手順は plan/依存で足りる。

## 対処（決めたら）
それぞれ独立タスク（T-…）へ。1 は DESIGN を先に。2 は依存追加の判断から。3 は status レンダラの小拡張。
本 ISS は「やらない」でなく「設計判断つきで分離＝後続で拾う」の記録（DEC-0010 の理想形の残り）。
