---
id: EP-33
kind: epic
status: done
plan: detailed
requirements: [REQ-001]
depends_on: []
created: 2026-07-10
---
# EP-33 昇格と復旧（champion を正しく選び、間違えたら戻せる）

## 何が問題か（実測で再現済み）
1. **`champion()` は `sorted(glob("promotions/*.yaml"))[-1]`**。ASCII で数字は英字より前に並ぶので、
   `version:` が実在版を指す `notes.yaml` を 1 つ置くだけで、**劣る版が champion になり、serve がそれを配信する**。
   （`version` キーの無いただのメモ yaml は `KeyError` で騒ぐ。黙ってすり替わるのは前者だけ。）
2. **同じコードが `ds/models.py` と `agent/store.py` に構造同一で複製されている**（`champion()` の差は
   3 行の型名・関数名のみ）。同じバグを 2 か所で直す状態。
3. **`rollback` / `demote` が存在しない**（`src/` `docs/` 全体の grep で、`gates.py` のエラー文 1 件のみ）。
   `change_threshold` は厳密な改善だけを認めるので、**旧良版は永久に再昇格できない**。
   `gates.py` が「champion の切り戻しが要る」と言うその操作が、実在しない。

## 順序の拘束（ここを間違えると悪化する）
`champion()` に「異物 yaml があれば `ValueError`」を先に入れると、**切り戻しの唯一の手段を塞ぐ**。
rollback が無い今、`promotions/` に手書き yaml を置くことだけが切り戻しの手段だからである。
「異物 yaml の脆弱性」と「rollback の不在」は同じ穴の両面で、後者が前者を誘発している。

したがって **T-0173（中核へ 1 本化）→ T-0175（rollback を一級の操作に）→ T-0174（alias と異物拒否）** の順を守る。

## 復旧という次元（目的の定式化に足りなかったもの）
「正しい答えを速く出す」だけを目的に書くと、**間違えた後に戻すまでの時間**が視野に入らない。
rollback の不在はこの次元の欠落そのもの。目的には「間違いを特定して戻せること」を含める（T-0189）。

## 設計
`src/harness/promotion.py`（中核。stdlib＋`harness.storage`＋`harness.gates` のみに依存）。
`storage.py` と同じ方針で**仕組みだけを持ち、方針は呼び手が持つ**。

- 仕組み：記録の置き場・読み書き・champion の解決・判定の実行。
- 方針：どのレジストリで指標の向きを解決するか（ds は `METRICS`・agent は `AGENT_METRICS`）、
  primary に何を選ぶか、閾値をいくつにするか。呼び手が解決してから渡す。
- 昇格記録に `kind: promote | rollback` を持たせる。**rollback は昇格ではないので判定を通さない**
  （`change_threshold` を免除する）。語の出典は SageMaker Model Registry の `ModelApprovalStatus`。
- `champion()` の走査は `VERSION_FORMAT` に一致するファイル名だけに限定し、
  **一致しない yaml が `promotions/` に居たら `ValueError`**（無視でなく失敗＝fail closed）。

これで agent は ds を import しないまま複製を捨てられる（境界は壊れず、むしろ強くなる）。

## タスク
| ID | 何を | 順 |
| --- | --- | --- |
| T-0173 | 昇格の保存機構を `harness/promotion.py` へ 1 本化する（挙動は変えない） | 1 |
| T-0175 | `rollback` を一級の操作にする。ds に promote/champion の CLI を足す（agent との非対称を消す） | 2 |
| T-0174 | champion を alias で指す。異物 yaml は `ValueError` | 3 |
