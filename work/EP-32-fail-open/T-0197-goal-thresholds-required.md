---
id: T-0197
kind: task
status: done
title: goal.yaml の thresholds 省略を ValueError にする
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_agent_judge.py::test_goal_from_mapping_empty_thresholds_raises
  - tests/test_agent_judge.py::test_goal_from_mapping_missing_thresholds_key_raises
  - tests/test_agent_judge.py::test_goal_from_mapping_nonempty_thresholds_still_passes_through
  - tests/test_agent_goal.py::test_goal_yaml_without_thresholds_is_rejected_before_any_output_can_pass
---
# T-0197 goal.yaml の thresholds 省略を ValueError にする

## 何が問題か
`uv run agent run --spec … --goal goal.yaml` は一次 CLI 経路。`goal.yaml` に `thresholds:` を
書き忘れると、`src/harness/agent/goal.py` の `goal_from_mapping`（旧 203 行付近）が黙って
`thresholds = {}` を補っていた。`eval.passes(scores, {})` は判定 0 件なので `True` を返し、
でたらめな出力でも cycle 1 で `GoalGate.check(...)` が `stop=True, reason="goal_met"`・CLI は
exit 0 になっていた。

AGENTS の看板保証（「完了を自己申告できない」）が、悪意ゼロ・守られたファイルへの差分ゼロ・
書き忘れ 1 行で無音のまま消える。CLI の `--goal-expected` 側は省略時に `{"exact_match": 1.0}` へ
倒す（`agent/cli.py` の `_parse_thresholds` 呼び出し箇所）のに対し、**YAML 側だけが `{}` に
倒れる非対称**が、見落としの証拠だった。

## やること
`goal_from_mapping` で `thresholds` が空（キー無し・空辞書のどちらも）なら `ValueError` にする。
goal の存在意義は停止のゲートなので、閾値ゼロの goal は無意味。検出器ではなく**発生源の封鎖**
（AGENTS の「概念に 2 つ目の名前を作らない」等と同じ「入口を塞ぐ」形の是正）。

エラーメッセージは、何を書けばよいかが分かる形にする（宣言できる指標名の候補を
`AGENT_METRICS` から出す。`Registry.resolve` の未知 kind エラーの書き方に合わせる）。

## やらないこと
- `gates.evaluate` に「空 specs なら ValueError」を入れない。`ds.eval.passes(x, {})` が True を
  返すのは意図された仕様で、`tests/test_ds_eval.py` がコメント付きで固定している。「まず回して
  指標を見る」探索は正当な経路。`evaluate` を一律で落とすと ds の探索が全滅する。**直すのは
  `goal_from_mapping` の 1 か所だけ。**
- `thresholds` と `metrics` の集合等式（全 metrics に閾値必須）を強制しない。観測目的で測る
  指標（brier・calibration_gap 等）に形だけの閾値を書かせることになり、「構成から導けない数値」
  を機構が量産する。要求するのは「空でないこと」だけ。
- 頼まれた範囲の外（`gates.py`・CLI の `--goal-expected` 経路・その他プロファイル）を変更しない。

## 受け入れ基準
- `thresholds: {}` を明示した goal 宣言は `goal_from_mapping` で `ValueError`。
- `thresholds` キーそのものが無い goal 宣言も `goal_from_mapping` で `ValueError`（同じ扱い）。
- 非空の `thresholds` は従来どおり通る（既存の goal 宣言・テストが壊れない）。
- 退行テスト：`thresholds` を省略した `goal.yaml` を `load_goal` に渡すと、`GoalGate` が
  作られる前に `ValueError` になる＝でたらめな出力が `goal_met` になる経路が発生源で塞がれる。
- `uv run verify` が全成功。
