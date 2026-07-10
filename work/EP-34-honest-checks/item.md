---
id: EP-34
kind: epic
status: in-progress
title: 誠実な検査（機械検査を名乗る仕組みが実は空振りしている箇所を塞ぐ）
plan: outline
requirements: []
depends_on: []
created: 2026-07-10
---
# EP-34 誠実な検査

## 何をするか
「機械が検出する」を名乗る検査（doclint・coverage_lint 等）のうち、判定の作法が粗く**実質的に空振り**
しているものを見つけ、判定の精度だけを上げる（対象集合の導出方法・検査の目的は変えない）。

## 背景
`src/harness/coverage_lint.py`（CLI コマンドの導線カバレッジ検査）は「スキル/正本 docs から到達できる
か」を `token in corpus`（部分文字列一致）で判定していた。この作法だと、1 語のコマンド名（`serve`・
`status` 等）は本文にただ出現するだけで常に合格し、否定文中の出現（「〜を直接叩かない」等）も導線に
数えてしまう。モジュールの docstring 自身が「部分文字列一致」であることを自認しており、検査が
(b)（機械が検出する）を名乗りながら実質は空振りしている。

## タスク
- T-0201: coverage_lint の照合を `uv run <token>` の語境界つき正規表現に変える（詳細は同ファイル）。
