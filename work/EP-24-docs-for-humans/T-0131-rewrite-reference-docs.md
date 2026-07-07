---
id: T-0131
kind: task
status: done
title: Reference/プロファイル文書（agent/serve/ops＋スキル導線）を人間可読に刷新＋doc_standardsに導入検査を追加
created: 2026-07-07
depends_on: [T-0130]
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0131 プロファイル文書の刷新（全体像→詳細・標準用語）

## 狙い
`docs/agent.md`・`docs/serve.md`・`docs/ops.md`（＋ serve/agent スキル）を、人が初見で理解できる Reference に
書き換える。書き換え後に `doc_standards` へ「可視の平易な導入で始まる」検査を足し、緑を保つ（骨組み→本実装）。

## 書き換えの原則（DEC-0019 に従う）
1. **全体像→詳細**：各文書は H1 直後に**可視の平易な導入**（2〜4 文）を置く：これは何か／なぜ在るか／誰が
   読むか。機構（モジュール名・レジストリ名）の羅列より前に置く。HTML コメントに隠さない。
2. **Diátaxis を意識**：これらは Reference（事実・契約）。「使い方（How-to）」節と「契約（Reference）」節を
   区別し、「なぜ（Explanation）」は最小限にして DEC へリンク。
3. **標準用語＋用語集リンク**：造語は標準語（英/カナ）にするか初出で定義。初出時に `docs/glossary.md` の該当
   語へリンク（例 `[champion](glossary.md#champion)`）。champion・shadow deployment・PSI・canonical JSON・
   provenance/lineage・idempotent・maker-checker などは標準語で。`AgentSpec`・`cassette`・`effort`・`goal-based`
   は初出で 1 文の説明＋用語集リンク。
4. **長文の分割**：3 つ以上の入れ子括弧・1 文が複数行にわたるものは箇条書き・短文に割る（監査指摘：
   agent.md の冒頭モジュール羅列、serve.md の shadow 監視注意、ops.md の 1 文詰め込み）。
5. **過不足なく**：DEC 参照は「なぜ」を 1 語で済ませる飾りにしない。理由が読者に必要なら 1 文で述べ、詳細は
   リンク。冗長な重複は削る。情報は減らさない（契約・キー・型は保つ）。

## 具体
- **`docs/agent.md`**：冒頭にモジュール羅列でなく「LLM エージェントを宣言（プロンプト＋モデル＋ツール＋方針）
  として持ち、golden set で採点し、基準を満たした版だけ champion に昇格して配信・監視する仕組み」の平易な導入。
  用語（AgentSpec, golden set, cassette, goal-based gate, effort, loops）を初出で 1 文＋用語集リンク。契約表
  （ログ行など）は Reference として保つ。
- **`docs/serve.md`**：冒頭に「学習済みモデルの現行版（champion）を FastAPI で配信し、予測を来歴つき JSONL に
  記録する」導入。champion/registry/昇格/prediction log/shadow deployment/role を初出で定義＋用語集リンク。
  shadow 監視の注意（現 72-75 行の長文）を箇条書きに割る。
- **`docs/ops.md`**：冒頭に「配信の後工程＝CI ゲート・継続学習(CT)・リリース戦略・監視の閉ループを扱う」導入。
  PROFILE/pm_checks/PSI/band/门番 を平易に。CT・PSI は初出でスペルアウト。
- **serve/agent スキル**（`.claude/skills/serve/SKILL.md`・`.claude/skills/agent/SKILL.md`）：エージェント用の
  手順は保ちつつ、人が読んでも意味が分かるよう用語を用語集に合わせる（過度な内部略語を避ける）。
- **`doc_standards` に導入(lede)検査を追加**：`docs/*.md`（archive・glossary・README 除外、または対象を
  明示リストで）の H1 直後の最初の内容ブロックが、見出しでも箇条書きでも HTML コメントでもなく**平文の
  段落**であること（＝可視の導入）。違反＝error。理由必須 allowlist。現リポの全対象文書が緑になるよう、
  対象文書は本タスク＋T-0132 で導入を持つものに限定して段階導入してよい（対象リストの根拠をコメントで明記）。

## テストの要点
- lede 検査：一時 doc の H1 直後がいきなり箇条書き／HTML コメント→error、平文段落→緑（構成から導出）。
- 現リポ回帰：`doc_standards.run_checks(REPO_ROOT)` が空（刷新済み文書が lede を持つ＝緑）。
- 既存 T-0130 のテストは緑のまま。markers 必須。

## 触ってよい範囲
`docs/agent.md`・`docs/serve.md`・`docs/ops.md`・`.claude/skills/serve/SKILL.md`・`.claude/skills/agent/SKILL.md`・
`docs/glossary.md`（用語追記のみ）・`docs/README.md`（地図の追補のみ）・`src/harness/doc_standards.py`・
`tests/test_doc_standards.py`・この item.md。契約（キー・型・CLI）は意味を変えない。
