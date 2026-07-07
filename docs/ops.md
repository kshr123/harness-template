# ops — 運用プロファイル（CI・継続学習・リリース戦略・監視の閉ループ）の正本

学習ハーネスの「配信の先」＝運用（CI の verify ゲート・継続学習・リリース戦略・監視→課題起票）を
扱うプロファイル（EP-21・DEC-0014 の対象範囲）。実装は `src/harness/ops/`（profile.py＝検査の結線・
ci_lint.py＝CI テンプレートの構造 lint）。中核へは `.harness/config.toml` の
`profiles = [..., "harness.ops"]` 経由で PROFILE（検査の結線）だけを見せる（DEC-0004 のプロファイル境界・
DEC-0013 の軽 import）。**ops は CLI を持たない**＝入口はこの正本と pm_checks（`uv run verify` に自動で乗る）。

## 思想（実行しない）

GitHub Actions・k8s・スケジューラ・クラウドは**実行しない**。運用の実行基盤は利用者環境の関心であり、
当リポが持つのは：

- **テンプレート**（`templates/ci/` に置く雛形。T-0111 以降で追加）＝利用者がコピーして使う資産。
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

（T-0111 で記載：`templates/ci/` の verify ワークフロー雛形の複製手順・ci_lint が何を守るか＝
verify step の有無・Python 版・extras の整合。）

## リリース戦略（Blue-Green・Canary）

（T-0112 で記載：既存の配信テンプレート `templates/serve/` の資産＝image tag 切替・replica 比率での
実現方法を明文化。コードは増やさない。）

## shadow 配信

（T-0113 で記載：`/predict` の 1 プロセス内分岐で champion と shadow 版を並走させ、
`role: primary|shadow` を予測 JSONL に記録する契約。`docs/serve.md` の契約表と同時に更新。）

## 継続学習（CT）雛形

（T-0114 で記載：schedule→experiment→monitor→閾値を満たせば promote の雛形と ci_lint の拡張。
既存部品の結線のみ。）

## 監視→課題起票の閉ループ

（T-0115 で記載：`data monitor --file-issue`＝PSI_ALERT 超で issues に冪等起票。門番にしない＝exit 0。）
