# 用語集（glossary）

このリポジトリで使う造語・内部用語を、平易な定義と標準用語（英語/カタカナ）に対応づける一覧。
文書・会話で内部用語を初めて使うときは、その場で定義するかここへリンクする（DEC-0019）。
項目の重複・定義の無い見出しは `doc_standards`（`uv run verify` の検査）が機械的に止める。

## 正本
ある事実・ルールの「唯一の正」とする置き場（英: source of truth／シングル・ソース・オブ・トゥルース）。
同じ内容を 2 か所に書かず、他の場所はここへのリンクだけを置く。例：進め方の正本は `docs/method.md`。

## 導線
読者（人・エージェント）がある部品やコマンドの使い方に**たどり着けるリンク・記述**のこと
（英: discoverability／cross-reference。「入口への案内」）。導線が無い部品は存在しないのと同じ、が方針
（DEC-0009/DEC-0016）。書き忘れは coverage_lint が検出する。

## 入口
部品を「元コードを読まずに使える」ようにするための公開口（英: entry point／エントリーポイント）。
レジストリ登録＋docstring＋スキル/雛形からの導線、の 3 点セットを指す（DEC-0009「部品は入口まで作って完了」）。

## 作業単位（item）
エピック・タスク・実験など、進捗管理の 1 まとまり（英: work item／ワークアイテム）。`work/` の中のフォルダ
（`item.md` 付き）またはファイル 1 つで表し、frontmatter（id・kind・status など）を持つ。

## 歩く骨組み
入力→処理→出力→検証が端から端まで一巡する**最小の実装を先に作る**進め方（英: walking skeleton／
ウォーキングスケルトン）。検証を緑に保ったまま、各部を本実装に差し替えていく（`docs/method.md` A 節）。

## 昇格（気づき→ルール）
作業中の気づき（learnings）に一般性があると判断したら、決定（DEC）を起こして機械検査・抽象・スキル・規約の
どれかに「格上げ」すること（英: promote a learning to a rule）。流れの正本は `docs/method.md` C 節。
次の「昇格（モデル/エージェント→champion）」とは**別の意味**なので文脈で区別する。

## 昇格（モデル/エージェント→champion）
評価済みの版が関門（絶対＝しきい値、相対＝現 champion に勝つ）を通ったときだけ champion（採用版）にすること
（英: model promotion／champion promotion）。実装は `promote_model`／`promote_agent`。
前の「昇格（気づき→ルール）」とは**別の意味**。

## 金メッキ
**実装の出力をそのままコピーした固定の期待値**を書いたテストのこと（入力の作り方から導出できない値＝
実装が変わると意味なく落ち、実装が間違っていても通る）。一般用語では「実装出力のスナップショットを期待値に
するアンチパターン」。※標準の "gold-plating"（過剰な作り込み）**とは別の意味**なので注意。

## 門番（blocking な検査）
不合格なら処理を止める検査（英: blocking gate／ブロッキングゲート）。例：`uv run verify`・昇格の関門。
対義は「門番にしない」＝**助言型**（英: advisory）：監視（monitor）は band を出すだけで exit code は常に 0
（分布ずれの解釈は文脈依存なので、自動停止せず人が読む）。

## 関門（昇格ゲート）
champion 昇格の合否判定（英: promotion gate）。**絶対**（メトリクスが宣言したしきい値を満たす。NaN は不合格＝
fail-closed）と**相対**（現 champion に primary メトリクスで勝つ）の 2 段で、両方を満たしたときだけ昇格する。
「門番」「関門」「gate」はどれもゲートの意で、門番＝blocking/advisory の別、関門＝昇格の 2 段判定を指す。

## band（重大度の帯）
監視の指標を「安定／要注意／大変化」の 3 段に区切った帯（英: severity band）。しきい値の連続値を
人が読める段階に落とす。band は門番にしない（exit 0 のまま。大変化での課題起票は `--file-issue`）。

## 指紋（fingerprint）
内容から計算するハッシュ値（英: fingerprint／content hash。正準 JSON の sha256）。データ・入力・プロンプトが
「同じものか」を機械で確かめる来歴の道具。実装は `src/harness/fingerprint.py`。

## 正準 JSON
同じデータからは常に同じバイト列になるよう、キー順・区切りを固定した JSON（英: canonical JSON／
カノニカル JSON）。指紋（ハッシュ）の入力を安定させるために使う。

## 来歴（lineage）
その成果物（モデル・予測・応答）が「どのデータ・設定・版から生まれたか」の記録（英: provenance／lineage、
プロビナンス／リネージ）。manifest・予測 JSONL・実験の results/ が担う。

## harness
この開発基盤そのもの。テストハーネス（test harness）の語感で、「品質をモデルや人の注意力でなく、
検証・決まりごと・部品という**枠組み**で担保する」仕組み一式を指す（パッケージ名 `src/harness/`）。

## profile
中核（core）に領域別の部品と検査を足す束（英: profile／プロファイル）。ds（データサイエンス）・serve（配信）・
agent（LLM）・ops（運用）があり、`.harness/config.toml` の `profiles` で有効化する。境界＝core はプロファイルを
import しない（DEC-0004）。

## champion
現在採用している版（本番に出す 1 つ。英: champion／チャンピオン）。champion/challenger 運用の標準用語で、
昇格の関門を通った版だけが champion になる。

## champion/challenger
現行版（champion）と挑戦者（challenger）を同じ条件で評価し、勝った方を採用する比較運用
（英: champion/challenger／チャンピオン・チャレンジャー方式）。相対関門はこの考え方の実装。

## shadow deployment
本番のリクエストを新版にも**並走**させ、応答は返さずログだけ残す下見運用（英: shadow deployment／
シャドー配信）。予測 JSONL に `role: shadow` の行として残る（`docs/serve.md` の shadow 配信節）。

## registry
学習・評価済みの版（モデル・エージェント）を登録しておく置き場（英: model registry／モデルレジストリ）。
`work/<ID>/models/`・`work/<ID>/agents/` 配下の manifest と昇格記録の総体で、champion（採用版）はここから
解決する。

## prediction log
配信中の予測を 1 行＝1 予測で JSONL に残すログ（英: prediction log／予測ログ）。モデル版・入力の指紋などの
来歴を含み、監視（`data monitor`）が唯一依存する契約。行スキーマの正本は `docs/serve.md`。

## role
予測ログの各行の役割を示すキー。`primary`（応答を返した champion）か `shadow`（並走した shadow 版）の
どちらかが**常に**入る（英: role。shadow deployment の行を突き合わせ・除外するのに使う）。

## AgentSpec
LLM エージェントの宣言（英: agent specification）。prompt・model・tools・方針（effort・max_turns など）を
1 つの YAML で表し、この宣言そのものをエージェントの実体として評価・保存・昇格する
（`src/harness/agent/spec.py`）。

## golden set
期待する出力（expected）つきの評価用の例集（英: golden set／ゴールデンセット）。エージェントの合否は
golden set 全体への採点の平均で決める（テストデータの LLM 版・回帰の基準）。

## cassette
実 API の応答を JSON に固定しておき、テスト時にネットワークなしで再生する記録再生フィクスチャ
（英: record-replay fixture。VCR の「カセット」の慣用）。記録が無いキーはエラー＝fail-closed
（`src/harness/agent/cassette.py`）。

## effort
LLM の推論の深さの指定（英: reasoning effort。low〜max）。現行モデルは temperature を受け付けないため、
再現性・品質の軸は effort を**宣言（AgentSpec）に固定**して作る（DEC-0015）。

## loops
「停止条件が満たされるまで作業サイクルを繰り返す」エージェント運用の語彙（trigger×stop×policy。
turn-based／goal-based／time-based／proactive の 4 類型）。正本は DEC-0017 と `docs/agent.md` の loops 節。

## goal-based gate
goal-based loop の停止判定（英: evaluator gate／評価器ゲート）。モデル自身の「終わった」（`end_turn`）を
そのまま信用せず、宣言済みの評価器が合格と言うまで続行させる（DEC-0017・`src/harness/agent/goal.py`）。

## fail-closed / fail-open
判定できない入力（欠損・NaN・未知キー）が来たとき、**不合格側に倒す**のが fail-closed（フェイルクローズド）、
合格側に素通しするのが fail-open（フェイルオープン）。合否・関門・再生は常に fail-closed に作る（L-009）。

## PSI
Population Stability Index（母集団安定性指標）。2 つの分布（基準と現在）のずれの大きさを 1 つの数にした
監視の定番指標。`data monitor` がドリフト検知に使い、band で読む。

## CT
Continuous Training（継続学習）。schedule（cron）→再学習→監視→関門を満たせば昇格、を既存部品の結線だけで
定期的に回す運用。雛形は `templates/ci/` の retrain.yml（正本は `docs/ops.md` の CT 節）。

## pm_checks
`uv run verify` が最初に走らせるプロジェクト管理検査の列（英: project-management checks。実体は
`harness.checks.PM_CHECKS`）。lint 群はここに登録されることで verify に乗り、プロファイルは PROFILE 経由で
自分の検査をこの列に足す。

## lint 群
実行せずに構造・整合を検査する軽い検査たちの総称：pm.lint／spec_lint（作業単位・SPEC の形）、
doclint（書いた参照の実在＝dead link）、coverage_lint（コマンド導線の欠落＝missing link）、data lint
（テーブル定義）、deploy_lint・ci_lint・schedule_lint（テンプレートの腐り）、agent の宣言 lint、
doc_standards（文書の発見可能性と整合）。すべて `uv run verify` に乗る。

## maker-checker
作る側（maker）と確かめる側（checker）を分ける原則（英: maker-checker／メーカー・チェッカー、
「四眼原則」）。実装した本人・同じ文脈のエージェントは自分で合否判定しない（AGENTS 第一原則）。

## ratchet
一度上げた基準を戻さないための歯止め（英: ratchet／ラチェット＝逆回転しない歯車）。ルールを昇格させるときは
**先に「違反すると失敗する検査」を書いてから直す**ことで、後のセッションが知らずに退行しても verify が止める。

## 冪等
同じ操作を 2 回以上行っても、1 回だけ行ったのと同じ結果になる性質（英: idempotent／アイデンポテント）。
例：monitor の課題起票は同じ事象では 2 件目を作らない。

## 案件
1 つの顧客プロジェクト・開発テーマ（英: project／engagement）。このテンプレートは「1 リポジトリ＝1 案件」で
複製して使う（`docs/template-copy.md`）。

## verify
完了判定の唯一の入口 `uv run verify`。プロジェクト管理の検査（lint 群）＋ruff＋mypy＋pytest をすべて走らせ、
**全成功したときだけ完了**とする（自己申告で完了にしない）。CI もローカルも同じ入口を使う。
