---
id: ISS-0007
kind: risk
state: open
found_in: ds-review-2026-07-05
created: 2026-07-05
title: 実験 config が型無しで、threshold と thresholds を取り違えても検知できない
---
# ISS-0007 実験 config が型無し（ExperimentSpec が無い）

## 事象
`run_experiment` は 12 個の緩い引数を取り、実験の設定（data/features/encode/model/task/n_folds/seed/thresholds…）は
`Mapping[str, Any]` として組み立て時に断片的に検証されるだけ。config トップレベルの型が無い。特に
`thresholds`（合否辞書）と `threshold`（決定境界の float）が兄弟引数で共存し、取り違えても機械検査が無い。
未知のトップレベルキーは黙って無視される。

## 根拠・影響
このリポは「config 駆動」を掲げ、`.harness/config.toml` とテーブル定義は既に pydantic v2（`extra="forbid"`）で
締めている。実験 YAML だけが型無しの config 面＝自己矛盾。エージェントが config をコピペ改変する前提なので、
静かに無視されるキーやタイポは実損に直結する。

## 対処の方針（決めてから）
`ExperimentSpec`（pydantic v2・`extra="forbid"`）を起こし `run_experiment`／`train.py` 雛形に通す。
`threshold` は `decision_threshold` へ改名して混同を断つ。experiment スキルの導線も更新（DEC-0009）。
