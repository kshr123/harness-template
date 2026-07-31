---
id: ISS-0020
kind: risk
state: resolved
created: 2026-07-31
closed: 2026-07-31
found_in: T-0302
promoted_to: T-0306
title: lintkit の未使用部品（Corpus/Rule/run/Exemptions クラス/word_bounded）は P4 で使うか撤回するかを決める前向き投資
---
> 解決（2026-07-31・T-0306）：「使う」で決着。word_bounded は code_doc_lint が、Corpus/Rule/run は checks.py の
> runner（`lintkit.run`）と Corpus ネイティブになった conventions が実際に使う。唯一 consumer の付かなかった
> Exemptions クラスだけは撤回（`validate_exemptions` は 4 lint が使うので残す）。lintkit に死蔵コードは無い。
lintkit（EP-54）の一部は既に実運用で使われている（`ids` は doclint・doc_source_lint が、
`exempt.validate_exemptions` は 4 つの lint が使う＝単一の出所）。一方で **`Corpus`・`Rule`・`run`・
`Exemptions` クラス・`ids.word_bounded`（と `NAME_BEFORE/NAME_AFTER`）はまだテストからしか使われていない**
前向き投資（新しい検査や後続フェーズが使う想定で先に置いた部品）。core.md に「新しい検査は lintkit を使う」
導線は書いたが、消費者はまだ 0。

基盤自身の原則「効かない決まりごとは撤回する」に照らすと、この未使用部品は次のどちらかに決着させる：

- **使う（P4-P6）**：`conventions` を 5 個の小ルール（`Rule`＋`Corpus.python_files`）へ／`ci_lint` から
  `lintkit.workflows` を抽出し `schedule_lint` を載せ替え／agent `lint` を AgentSpec バリデータへ。これらは
  検出を 1 つも落とさない変異確認を伴う guard 層の移行なので、集中した別パスで丁寧にやる（設計は fable の
  全体アーキテクチャ）。着手時に `Corpus.python_files`（P0 で先送りした対象集合の走査）を足す。
- **撤回する**：P4-P6 に着手しないと決めたら、`Corpus`・`Rule`・`run`・`Exemptions` クラス・`word_bounded` と
  それらのテスト・core.md の言及を撤去し、lintkit を実運用で使う `ids`＋`validate_exemptions` だけに絞る
  （YAGNI・未使用の抽象を残さない）。

対処すると決めたら `promoted_to` にタスク ID を書いて着手する。見送るなら wontfix＋理由（＝撤回を選ぶ）。
