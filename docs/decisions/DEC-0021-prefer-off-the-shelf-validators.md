---
id: DEC-0021
status: accepted
date: 2026-07-07
---
# DEC-0021 機械検査の第一候補は既製バリデータへ委譲する（自前 lint はプロジェクト固有意味論に限定）

## 状況（何を決める必要があったか）
自前 lint（`schedule_lint.py`・`ci_lint.py`）を実測すると、下層の3〜5割が汎用形式の再実装だった：
YAML の妥当性検査・cron フィールド数の数え上げ・workflow の `on:`/`permissions:` の型検査・「停止」の
日本語 grep。`schedule_lint.py` が踏んだ `on:` → bool `True` に化ける罠（pyyaml の YAML-1.1 仕様）は、
GitHub Actions 専用 lint の actionlint が 10 年前から解決済みの問題である。DEC-0006（標準ライブラリを
再発明しない）・DEC-0008（sklearn が十分ならブロックを作らない＝作る/使うの基準）はモデル・特徴量の層に
適用済みだが、同じ思想を**機械検査（lint）自身**にはまだ適用していなかった。「新しい機械検査を書く前に、
既製スキーマ/バリデータで表明できるかを問う」関門が無いと、汎用形式の再実装が積み上がり続ける。

## 検討した選択肢
- A：現状維持。自前 lint に汎用形式の検査（YAML 妥当性・cron 構文・workflow 型）を書き足し続ける。
- B：**機械検査を新設する前に「既製バリデータで表明できるか」を問う関門を DEC 化し、実際に配線する**。
  汎用形式（YAML 妥当性・workflow 構造の型・cron 構文・JSON Schema 準拠）は既製バリデータへ委譲し、
  自前 lint はスキーマで表明できないプロジェクト固有の意味論（scripts 実在・experiment→monitor→promote の
  順序・導線カバレッジ・参照実在・三者整合・停止手順の README 節との結線）だけに残す。
- C：自前 lint を全廃し既製バリデータのみに委縮する。→ プロジェクト固有意味論（DEC-0009 の導線カバレッジ等）は
  どのスキーマにも存在しないため既製バリデータでは表明不能。過剰な削減で守るべき検査が消える。

## 決定と理由
**B を採る**。判定表：

| 検査したいこと | 既製で表明できるか | 採る手段 |
| --- | --- | --- |
| YAML として妥当か | できる（yaml パーサ・スキーマバリデータの前提） | 既製（既存の `yaml.safe_load` 呼び出し・pre-commit の `check-yaml` 系） |
| GitHub Actions workflow の構文・式・cron 構文 | できる（actionlint が専用に持つ） | 既製：`rhysd/actionlint`（pre-commit フック `actionlint`） |
| workflow の `on:`/`jobs:`/`permissions:` の型・スキーマ準拠 | できる（schemastore の github-workflows スキーマ） | 既製：`check-jsonschema --builtin-schema vendor.github-workflows` |
| scripts（train.py 等）が実在するか | できない（このリポ固有のディレクトリ規約） | 自前（`ci_lint.py`） |
| experiment→monitor→promote の step 順序 | できない（このリポ固有の運用フロー） | 自前（`ci_lint.py`） |
| 「停止」手順が README の節と結線しているか | できない（自然文の意味論） | 自前（`schedule_lint.py`） |
| 新しい CLI コマンドの導線カバレッジ | できない（DEC-0016 の固有検査） | 自前（`coverage_lint.py`） |

理由：
- 既製バリデータは「汎用形式」を専門に持ち、罠（YAML-1.1 の bool 化等）を先取りして直してある。自前で
  同じ罠を踏み直すのはコストの割に価値が無い（DEC-0006 と同じ再発明回避の論理を lint 自身へ適用）。
- プロジェクト固有意味論（ディレクトリ規約・順序・導線・README 結線）はどの既製スキーマにも定義がなく、
  委譲先が存在しない。ここは自前で持ち続ける必要がある（C は過剰）。
- 配線は gitleaks と同じ remote repo フックの流儀（pre-commit 実行時のみ network・`uv run verify` は
  no-network のまま）に合流させ、新しい執行系を増やさない。

## 影響（良い点・悪い点・これからやること）
- 良い点：`.pre-commit-config.yaml` に actionlint・check-jsonschema（`vendor.github-workflows`）を配線
  （T-0134）。既製バリデータが汎用形式の罠を機械的に潰す。以後、新しい機械検査を書く前に本判定表を引く。
- 悪い点：この骨組みでは自前 lint の汎用層をまだ剥離しない（二重検査で緑）。純化（重複コードの削除）は
  T-0135 の領分。
- これからやること：T-0135 で `schedule_lint.py`・`ci_lint.py` から既製バリデータが代替した汎用形式の
  検査コードを剥離し、プロジェクト固有意味論だけを残す。関連 [[DEC-0006]] [[DEC-0008]] [[DEC-0016]]。
