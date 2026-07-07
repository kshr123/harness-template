# ops — 運用プロファイル（CI ゲート・継続学習・リリース戦略・監視の閉ループ）

モデル配信の「その後」＝運用を扱うプロファイル。中身は 4 つ：CI の verify ゲート、継続学習
（CT＝Continuous Training。定期的な再学習の自動化）、リリース戦略（Blue-Green・Canary）、
監視から課題起票までの閉ループ。運用の実行基盤（GitHub Actions・k8s・クラウド）そのものは動かさず、
利用者がコピーして使うテンプレートと、その腐りを止める静的検査だけを持つ。案件の運用を組む・CI/CT の
雛形を使うエンジニアが読む Reference（対象範囲の決定は DEC-0014）。

実装は `src/harness/ops/`：`profile.py`（検査の結線）・`ci_lint.py`（CI テンプレートの構造 lint）。
**ops は CLI を持たない**＝入口はこの正本と、`uv run verify` に自動で乗る検査
（そのプロファイルが公開する検査の集合＝pm_checks）だけ。中核へは `.harness/config.toml` の
`profiles = [..., "harness.ops"]` 経由で PROFILE（プロファイル＝検査と部品の束）の
検査だけを見せる（core はプロファイルを import しない境界＝DEC-0004・import を軽く保つ規律＝DEC-0013）。

## 思想（実行しない）

GitHub Actions・k8s・スケジューラ・クラウドは**実行しない**。運用の実行基盤は利用者環境の関心であり、
当リポが持つのは：

- **テンプレート**（`templates/ci/` の雛形）＝利用者がコピーして使う資産。
- **構造 lint**（`ci_lint.run_checks`）＝実行できない資産の参照整合を verify で静的に検査し、
  テンプレートが腐るのを止める（`src/harness/serve/deploy_lint.py` が `templates/serve/` を守るのと同型）。
- **プロファイル境界**＝ops を外したい案件は config の 1 行を消すだけ（中核・ds・serve は無傷）。
- **スキル・正本の導線**＝この文書（と関連スキル）から使い方に到達できる。

ci_lint はネットワーク 0・依存は stdlib＋pyyaml のみ。`templates/ci/` が無いプロジェクト
（テンプレートを同梱しないコピー先の案件）では何も指摘しない（誤検知しない）。

## やらないこと（利用者環境の関心・EP-21 の範囲外）

GitHub ランナー・k8s・クラウド基盤の実装／A/B テスト（実トラフィックの出し分け）／streaming（Kafka 等）／
S3・GCS の実装／retry・timeout・circuit breaker／オンライン特徴量ストア／prediction cache／gRPC。
理由と順序の判断は `work/EP-21-ops-profile/item.md` の「やらないこと」を参照。

## CI（verify ゲート）テンプレートと ci_lint

`templates/ci/.github/workflows/verify.yml` は、テンプレ複製先のリポジトリが **PR→`uv run verify` の
ゲート**を最初から持てる雛形。使い方：

- 複製先のリポジトリ直下へ `.github/workflows/verify.yml` としてコピーする。`templates/ci/` は雛形置き場で
  あり、当リポ自身の CI（`.github/workflows/ci.yaml`）とは独立（GitHub Actions はリポ直下の `.github/` しか
  読まないので、雛形のままでは実行されない）。
- 複製先が編集してよい箇所（既定ブランチ名・OS）は雛形内のコメントで示している。
- ジョブの中身はローカルの完了判定と同じ 1 本：checkout → uv セットアップ（Python 3.14）→
  `uv sync --all-extras` → `uv run verify`。完了の定義を CI とローカルで一致させる。

ci_lint（`src/harness/ops/ci_lint.py`。pm_checks 経由で `uv run verify` に自動で乗る・CLI は持たない）は、
この雛形を**実行せずに**構造検査して腐りを止める。error になるのは：

- 必須ファイル（`.github/workflows/verify.yml`）の欠落＝複製先がゲート無しで始まってしまう。
- `uv run verify` を実行する step が無い＝ゲートの本体が抜けた雛形。
- `python-version` がリポの正（pyproject の `requires-python`）と食い違う・指定が無い＝CI とローカルで
  別の版を検証してしまう。
- `uv sync` の step に `--all-extras` が無い＝optional 依存のテストが skip され「verify 環境は全部入り」
  （AGENTS の規約）に反する。

検査対象はデータ駆動（ci_lint の `_WORKFLOWS` の表）：ワークフロー雛形を足すときは表に 1 行足すだけで
欠落・必須 step・版/extras の検査が増える（下の retrain.yml も同じ表に載る）。`templates/ci/` が無い
コピー先の案件では何も指摘しない（誤検知しない）。

## リリース戦略（Blue-Green・Canary）

新しい仕組みは持たない：既存の配信テンプレート `templates/serve/` の資産だけで実現する。

- **Blue-Green**＝deployment の image tag 切替。model-in-image は「イメージ＝配る版」なので、戻すのも
  tag を戻すだけ＝即ロールバック。
- **Canary**＝同じ Service selector に載せた新旧 2 つの Deployment の replicas 比率で流量を近似的に分ける
  段階リリース。

コピペ手順・ロールバック手順・引用する k8s キーの正は `templates/serve/README.md` の「リリース戦略」2 節
（Blue-Green・Canary）。節構造と引用キーの実在は `tests/test_release_docs.py` が verify で検査する
（文書の腐りを止める）。実トラフィックの出し分け・外部指標収集を伴う A/B テストは配信基盤の関心＝やらない
（上の「やらないこと」）。

## shadow 配信

`/predict` の **1 プロセス内分岐**で champion（primary）と
shadow deployment（新版の並走・応答は返さずログだけ残す下見運用）を回す：

- 応答は常に primary のみ。同じ入力の予測を `role: primary|shadow` の 2 行として同じ予測 JSONL に残す
  （同じ `request_id`・`input_fingerprint` で突き合わせられる＝新版の本番下見）。
- 有効化は env（`SERVE_SHADOW_NAME` ほか）だけ。未設定なら従来どおり。
- shadow の失敗は primary に波及させない（ベストエフォート）。
- 契約（env・JSONL の `role`・失敗時の方針）の正本は `docs/serve.md` の「shadow 配信」節と契約表。
- 実行時基盤でのトラフィック分割・サイドカー等には踏み込まない（上の「やらないこと」）。

## 継続学習（CT）雛形

`templates/ci/.github/workflows/retrain.yml` は、**schedule（cron）→ experiment（再学習）→ `data monitor`
（ドリフト確認）→ 閾値を満たせば promote** を**既存部品の結線だけ**で回す雛形。新しい学習・監視・昇格の
仕組みをワークフローには書かない。使い方：

- 複製先のリポジトリ直下へ `.github/workflows/retrain.yml` としてコピーする。
- 雛形内の「← 複製先が編集する箇所」を差し替える：cron の周期・実験フォルダ（train.py と variant）・
  監視の基準テーブル id・promote の thresholds/primary。
- 手動起動（`workflow_dispatch`）も付いている（初回・障害後のやり直し用）。

各 step が呼ぶのはすべて既存部品：

- **再学習**＝実験雛形の `code/train.py`（config→学習→評価→保存→results/ を一気通貫。作り方は
  experiment スキル。学習コードをワークフローに書かない＝config.yaml が変種・モデル・データの正本）。
- **ドリフト確認**＝`uv run data monitor --baseline <テーブル id>`。**門番にしない**：分布ずれは
  band（安定/要注意/大変化の 3 段の帯）で人が読み、exit 0（基準テーブルが
  読めないときだけ非 0）。ドリフトの解釈は文脈依存で、誤検知の自動停止は再学習ループ全体を止めてしまう
  ため。閉ループ（大変化での課題起票）は `--file-issue` を付けて接続する（下の「監視→課題起票の閉ループ」節）。
- **昇格**＝`harness.ds.models.promote_model` が唯一の関門：絶対
  （thresholds＝`eval.passes` と同じ合否の辞書。「本番に出してよい最低ライン」を書く）かつ相対
  （現 champion に primary で勝つ）を満たすときだけ champion を更新する。版は手書きしない＝再学習 step の
  結果記録（`results/metrics_<variant>.yaml` の `model.name`/`model.version`）から結線する。関門で不合格なら
  step が落ちる＝昇格なし（意図した停止）。

verify.yml と違い retrain.yml は**任意**の雛形：ci_lint は**不在を error にしない**（CT を回さない複製先を
誤検知しない）。在るときだけ次を静的検査して腐りを止める（`_WORKFLOWS` の表の `required=False` の 1 行。
存在検査＝`required`、内容検査＝`required_runs`、順序＝`ordered`、トリガ＝`required_triggers` を表の列で
区別する）：

- schedule トリガの有無。
- experiment→monitor→promote の step の**有無と登場順**（`ordered=True`。監視してから昇格の順序が意味を
  持つので、monitor↔promote を並べ替えると順序違反で error）。
- Python 版・`--all-extras`。

### loops 語彙での位置づけ（time+goal 合成・T-0120）

- **trigger = time**：`schedule.cron`（定期）＋`workflow_dispatch`（手動やり直し）。
- **stop は 2 層**：(i) 1 周の停止＝`promote_model` 関門（絶対 thresholds＝ds `eval.passes` と同じ合否＋
  相対＝champion 越え）。合格→champion 更新で退場・不合格→step が落ちて昇格なしで退場、どちらでも 1 周は
  必ず終わる（monitor は門番にしない＝stop に関与しない、を再掲）。(ii) ループ全体の停止＝workflow 無効化・
  cron 削除（停止規律の正本は `docs/agent.md` の time-based routine の停止節＝T-0097。重複記述しない）。
- **policy**：`retrain.yml`（結線の正本・ci_lint が構造検査）×実験フォルダの `config.yaml`（何を再学習
  するか）×thresholds/primary（合格ライン）。
- **周回（閉ループ）**：前半円＝`data monitor --file-issue`（ドリフト→冪等起票・exit 0）、後半円＝
  schedule→train→promote 関門。agent 版 proactive 閉ループ（`docs/agent.md` の proactive 節＝T-0098）と
  対称（重複記述しない）。
- **同型性＋実装非共有**：agent の goal ゲート（`GoalGate`＝`AGENT_METRICS`＋agent `eval.passes`）と
  promote 関門（`promote_model`＝ds `eval.passes`〔絶対〕＋champion 越え〔相対〕）は同じ形＝「宣言済みの
  成功基準を、作った側とは別の評価器が検査して合格したときだけ先へ進む」（AGENTS 第一原則の機械化）。
  差分（同型≠同一）：goal ゲートは同一プロセス内で未達なら続行注入して反復・promote 関門はステートレスな
  1 周で退場（続行は次周の schedule）。実装は共有しない（DEC-0004・`eval.passes` の agent/ds 併存は意図
  した複製・共有したくなったら DEC-0012＝DEC-0018 の再判断トリガ）。
- **実コード消費なしの確定**：(a) 実行体は GitHub Actions（利用者環境）＝`check()` を呼ぶ主体がハーネス側
  に無い。(b) 各 scheduled run はステートレスな 1 周＝プロセス内に反復が実在しない（反復を統べるのは
  cron）。(c) 停止は `promote_model` が既に完全に持つ＝StopCondition を挟むと判定の正本が二重になる
  （DEC-0004 違反への入口）。`loops.py` の import は不要（T-0120 で確定・DEC-0018）。

## 監視→課題起票の閉ループ

`uv run data monitor --baseline <テーブル id> --file-issue` は、PSI
（Population Stability Index＝母集団安定性指標。分布のずれを 1 つの数にした監視の定番指標）の band が
大変化（`PSI_ALERT`＝0.25 以上）の列があるとき、issues の登録簿（`uv run issue` と同じ置き場・
`.harness/config.toml` の issues.backend）へ**冪等に**（同じ事象では 2 件目を作らずに）
起票する（kind=risk・state=open）。

- **処理を止める検査（門番）にはしない**：起票は副作用で exit code は常に 0
  （alert でも・起票済みでも 0。分布ずれで CI・再学習ループを止めない）。
- `--file-issue` 無しの出力・exit code は従来と完全に同一（既定 off＝後方互換）。
- 既存 2 部品の合成のみ：判定は `ds/monitor.py` の psi/band、起票は `issues.py` の既存 API
  （local_dir・next_id）＝新しい監視ロジック・新しい backend を作らない。

詳細：

- **冪等**：課題本文の「監視指紋」（基準テーブル id×大変化の列集合の正準 JSON の sha256＝
  `harness.fingerprint.input_fingerprint`）を open / in-progress の課題と照合し、既にあれば起票しない
  （`起票済み: ISS-xxxx` と 1 行出すだけ）。psi 値・日付は指紋に**含めない**＝同じドリフト事象の再実行・
  翌日の再実行で重複起票しない。列集合が変われば別事象として新規に起票される。
- **起票の中身**：タイトル・本文は決定的（対象列・psi 値・基準/ログの指定・日付）。対応すると決めたら
  `promoted_to` で作業単位（再学習・特徴の見直し）に結びつける（課題の生涯・検査は `uv run issue check`）。
- **backend**：github: backend では（`issue new` と同様）起票は GitHub 側で行う＝その旨を 1 行出して
  監視は継続する（exit 0）。
- **shadow との併用**：`data monitor` は既定 `--role primary`（shadow 行を除外した従来相当の集計。
  詳細は docs/serve.md の shadow 配信節）。
- **CT への結線**：retrain.yml（上の CT 雛形）の monitor step に `--file-issue` を付ければ、定期実行の
  ドリフト検知が課題登録簿に自動で残る（読む・対応を決めるのは人＝自動停止しない）。
