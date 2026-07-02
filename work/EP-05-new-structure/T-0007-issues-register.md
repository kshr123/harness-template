---
id: T-0007
kind: task
status: done
title: 課題の登録簿（issues/ ＋ uv run issue ＋ 整合検査）
requirements: [REQ-003]
verified_by: [tests/test_issues.py]
depends_on: [T-0005, T-0006]
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0007 課題の登録簿

## 目的
発見された問題・リスク・疑問を、作業単位の木とは別の登録簿で扱う。置き場は設定で切り替え（この段階はローカル）、
対処すると決めた課題を作業単位へ昇格（promoted_to）で結びつけ、紐付けの崩れを検査する。未対処の課題は STATUS の
「人の判断待ち」に集約する。

## 受け入れ基準
- `issues/ISS-xxx.md` を読み、種別・状態・promoted_to を持つ課題として扱える。
- 整合検査（resolved なのに対応先が done でない／対応先が無い／done なのに未解決／見送りに理由が無い）が `uv run verify` に含まれ、失敗を検出する。
- 未対処（open）の課題が `uv run status` の「人の判断待ち」に現れる。
- `github:` backend ではローカルの実体を読まない（インターフェースは固定・実アダプタは後続）。
- `uv run verify` にすべて成功する。
