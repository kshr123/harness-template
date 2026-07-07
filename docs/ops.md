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

（T-0113 で記載：`/predict` の 1 プロセス内分岐で champion と shadow 版を並走させ、
`role: primary|shadow` を予測 JSONL に記録する契約。`docs/serve.md` の契約表と同時に更新。）

## 継続学習（CT）雛形

（T-0114 で記載：schedule→experiment→monitor→閾値を満たせば promote の雛形と ci_lint の拡張。
既存部品の結線のみ。）

## 監視→課題起票の閉ループ

（T-0115 で記載：`data monitor --file-issue`＝PSI_ALERT 超で issues に冪等起票。門番にしない＝exit 0。）
