# ops — 運用プロファイル（CI・継続学習・リリース戦略・監視の閉ループ）の正本

学習ハーネスの「配信の先」＝運用（CI の verify ゲート・継続学習・リリース戦略・監視→課題起票）を
扱うプロファイル（EP-21・DEC-0014 の対象範囲）。実装は `src/harness/ops/`（profile.py＝検査の結線・
ci_lint.py＝CI テンプレートの構造 lint）。中核へは `.harness/config.toml` の
`profiles = [..., "harness.ops"]` 経由で PROFILE（検査の結線）だけを見せる（DEC-0004 のプロファイル境界・
DEC-0013 の軽 import）。**ops は CLI を持たない**＝入口はこの正本と pm_checks（`uv run verify` に自動で乗る）。

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
ゲート**を最初から持てる雛形。複製先のリポジトリ直下へ `.github/workflows/verify.yml` としてコピーする
（`templates/ci/` は雛形置き場であり当リポの CI＝`.github/workflows/ci.yaml` とは独立。GitHub Actions は
リポ直下の `.github/` しか読まないので、雛形のままでは実行されない）。複製先が編集してよい箇所
（既定ブランチ名・OS）は雛形内のコメントで示している。ジョブの中身はローカルの完了判定と同じ
checkout→uv セットアップ（Python 3.14）→`uv sync --all-extras`→`uv run verify` の 1 本＝完了の定義を
CI と一致させる。

ci_lint（`src/harness/ops/ci_lint.py`。pm_checks 経由で `uv run verify` に自動で乗る・CLI は持たない）は、
この雛形を**実行せずに**構造検査して腐りを止める。error になるのは：

- 必須ファイル（`.github/workflows/verify.yml`）の欠落＝複製先がゲート無しで始まってしまう。
- `uv run verify` を実行する step が無い＝ゲートの本体が抜けた雛形。
- `python-version` がリポの正（pyproject の `requires-python`）と食い違う・指定が無い＝CI とローカルで
  別の版を検証してしまう。
- `uv sync` の step に `--all-extras` が無い＝optional 依存のテストが skip され「verify 環境は全部入り」
  （AGENTS の規約）に反する。

検査対象はデータ駆動（ci_lint の `_WORKFLOWS` の表）：ワークフロー雛形を足すときは表に 1 行足すだけで
欠落・必須 step・版/extras の検査が増える（T-0114 の retrain.yml も同じ表に載る）。`templates/ci/` が無い
コピー先の案件では何も指摘しない（誤検知しない）。

## リリース戦略（Blue-Green・Canary）

新しい仕組みは持たない：既存の配信テンプレート `templates/serve/` の資産だけで実現する。
**Blue-Green**＝deployment の image tag 切替（model-in-image は「イメージ＝配る版」なので、戻すのも
tag を戻すだけ＝即ロールバック）。**Canary**＝同じ Service selector に載せた新旧 2 つの Deployment の
replicas 比率で流量を近似的に分ける段階リリース。コピペ手順・ロールバック手順・引用する k8s キーの正は
`templates/serve/README.md` の「リリース戦略」2 節（Blue-Green・Canary。節構造と引用キーの実在は
`tests/test_release_docs.py` が verify で検査＝文書の腐りを止める）。実トラフィックの出し分け・
外部指標収集を伴う A/B テストは配信基盤の関心＝やらない（上の「やらないこと」）。

## shadow 配信

`/predict` の **1 プロセス内分岐**で champion（primary）と shadow 版を並走させる：応答は常に primary のみ・
同じ入力の予測を `role: primary|shadow` の 2 行として同じ予測 JSONL に残す（同じ `request_id`・
`input_fingerprint` で突き合わせられる＝新版の本番下見）。有効化は env（`SERVE_SHADOW_NAME` ほか）だけで、
未設定なら従来どおり。shadow の失敗は primary に波及させない（ベストエフォート）。契約（env・JSONL の
`role`・失敗時の方針）の正本は `docs/serve.md` の「shadow 配信」節と契約表。実行時基盤での
トラフィック分割・サイドカー等には踏み込まない（上の「やらないこと」）。

## 継続学習（CT）雛形

`templates/ci/.github/workflows/retrain.yml` は、**schedule（cron）→experiment（再学習）→`data monitor`
（ドリフト確認）→閾値を満たせば promote** を**既存部品の結線だけ**で回す雛形（新しい学習・監視・昇格の
仕組みをワークフローに書かない）。複製先のリポジトリ直下へ `.github/workflows/retrain.yml` としてコピーし、
雛形内の「← 複製先が編集する箇所」を差し替える：cron の周期・実験フォルダ（train.py と variant）・監視の
基準テーブル id・promote の thresholds/primary。手動起動（`workflow_dispatch`）も付いている（初回・
障害後のやり直し用）。各 step が呼ぶのはすべて既存部品：

- **再学習**＝実験雛形の `code/train.py`（config→学習→評価→保存→results/ を一気通貫。作り方は
  experiment スキル。学習コードをワークフローに書かない＝config.yaml が変種・モデル・データの正本）。
- **ドリフト確認**＝`uv run data monitor --baseline <テーブル id>`。**門番にしない**（分布ずれは band で
  人が読む・exit 0。基準テーブルが読めないときだけ非 0）＝ドリフトの解釈は文脈依存で、誤検知の自動停止は
  再学習ループ全体を止めてしまうため。閉ループ（PSI_ALERT 超で課題起票）は `data monitor --file-issue`
  （T-0115）がここに接続される。
- **昇格**＝`harness.ds.models.promote_model` が唯一の関門：絶対（thresholds＝`eval.passes` と同じ合否の
  辞書。「本番に出してよい最低ライン」を書く）かつ相対（現 champion に primary で勝つ）を満たすときだけ
  champion を更新する。版は手書きしない＝再学習 step の結果記録（`results/metrics_<variant>.yaml` の
  `model.name`/`model.version`）から結線する。関門で不合格なら step が落ちる＝昇格なし（意図した停止）。

verify.yml と違い retrain.yml は**任意**の雛形：ci_lint は**不在を error にしない**（CT を回さない複製先を
誤検知しない）。在るときだけ、schedule トリガの有無・experiment→monitor→promote の step の**有無と登場順**
（`ordered=True`＝監視してから昇格の順序が意味を持つので、monitor↔promote を並べ替えると順序違反で error）・
Python 版・`--all-extras` を静的検査して腐りを止める（`_WORKFLOWS` の表の `required=False` の 1 行。存在検査
＝`required`、内容検査＝`required_runs`／順序＝`ordered`／トリガ＝`required_triggers` を表の列で区別する）。

## 監視→課題起票の閉ループ

（T-0115 で記載：`data monitor --file-issue`＝PSI_ALERT 超で issues に冪等起票。門番にしない＝exit 0。）
