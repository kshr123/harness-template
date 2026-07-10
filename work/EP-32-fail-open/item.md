---
id: EP-32
kind: epic
status: in-progress
plan: outline
requirements: [REQ-001]
depends_on: [EP-27]
created: 2026-07-10
---
# EP-32 宣言の書き忘れを fail open にしない（goal-based 停止ゲート）

## 背景（実測済みの欠陥）
`uv run agent run --spec … --goal goal.yaml` は一次 CLI 経路。`goal.yaml` に `thresholds:` を
書き忘れると、`src/harness/agent/goal.py` の `goal_from_mapping` が黙って `thresholds = {}` を補う。
`eval.passes(scores, {})` は判定 0 件なので `True` を返し、でたらめな出力でも cycle 1 で
`stop=True, reason="goal_met"`・exit 0 になる。

AGENTS の看板保証（「完了を自己申告できない」）が、悪意ゼロ・守られたファイルへの差分ゼロ・
書き忘れ 1 行で無音のまま消える。

CLI の `--goal-expected` 側は省略時に `{"exact_match": 1.0}` へ倒す（`agent/cli.py`）。
**YAML 側だけが `{}` に倒れる非対称**が、見落としの証拠。

EP-27（T-0176）が昇格判定（`GATES`／`gates.evaluate`）側の fail-open を塞いだのに対し、
EP-32 は**goal-based 停止ゲート**（`agent/goal.py`）側の同種の穴を塞ぐ。両者は別のレジストリ・
別の呼び出し経路なので別の束にする。

## 方針
`gates.evaluate`／`ds.eval.passes(x, {})` の「空 specs なら True（探索目的で正当）」は仕様として
維持する（`tests/test_ds_eval.py` がコメント付きで固定）。直すのは**宣言の入口**
（`goal_from_mapping`）の 1 か所だけ：goal の存在意義は停止のゲートなので、閾値ゼロの goal は
無意味＝そこだけ `ValueError` にする（検出器でなく発生源の封鎖）。

## やらないこと
- `gates.evaluate` に「空 specs なら ValueError」を入れない（ds の探索経路を壊す）。
- `thresholds` と `metrics` の集合等式（全 metrics に閾値必須）を強制しない（観測用の指標に
  形だけの閾値を書かせることになる）。

## タスク
- T-0197：`goal_from_mapping` の thresholds 必須化。
