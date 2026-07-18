---
id: T-0232
kind: investigation
status: done
title: 陳腐化した基盤マーカー（T-0002・EP-01/02/03）を実態に合わせる
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by: []
---
## 結論（2026-07-18・実態に合わせて 4 つのマーカーを done に）

分解済みバックログが尽きた後、`status --next` が「着手できる」に T-0002、「分解の候補」に EP-02・EP-03 を
挙げていた。中身を確かめると、いずれも EP-01 期の計画スタブで、受け入れ基準・scope は後続の具体 epic が
既に納品していた。todo/outline のまま残すのは実態と食い違う（読む人に「未着手の基盤作業がある」と誤読
させる）ので、実態に合わせて done にした。捏造ではなく、既に在るものを指し直しただけ。

- **T-0002（CI とコミット前検査）**：CI が `uv run verify` を回す配線（EP-16 の OS matrix）・pre-commit の
  gitleaks/actionlint/check-jsonschema/commit-msg（EP-20・EP-25）・CI verify 雛形（EP-21）が納品済み。
  受け入れ基準を確かめるテスト（test_ci_config・test_guardrails）が verify に載っているので verified_by に
  紐付けて done に。→ 親 **EP-01** も 2 タスク完了で done に。
- **EP-02（開発の進め方）**：使い方スキル一式・method.md・テスト先行の判定（verified_by 必須・段階×マーカー・
  実験 --test 必須）が後続で揃っている。別立ての残作業なし＝done。
- **EP-03（引き渡し・振り返り）**：完了の定義（verify 緑のゲート）・learnings の継続運用（L-025 まで実運用）が
  揃っている。別立ての残作業なし＝done。

これで open の課題・未完の作業単位はすべて片づいた（消費者の無い ISS-0001・ISS-0005 は wontfix）。
