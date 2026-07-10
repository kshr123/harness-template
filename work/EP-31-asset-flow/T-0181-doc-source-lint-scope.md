---
id: T-0181
kind: task
status: todo
title: doc_source_lint の対象を templates/ と .claude/skills/ に広げる
created: 2026-07-10
depends_on: []
verified_by: []
---
# T-0181 恒久ファイルの範囲を実態に合わせる

## 何が問題か
`doc_source_lint` は「恒久ドキュメントが一時的な作業単位（`work/…`）を設計の根拠に参照しない」ことを
検査する（`work/` は複製時に消える／置き換わるので、根拠がリンク切れになる）。

ところが対象は `docs/*.md` の非再帰の glob だけ（`src/harness/doc_source_lint.py` の 60 行付近）。
**複製先に持っていかれる `templates/**` と、エージェントが必ず読む `.claude/skills/**` が対象外**。
守りたいもの（複製しても壊れない参照）に対して、検査範囲が一番効く場所を外している。

## 直し方
対象を 3 経路にする：`docs/*.md`（非再帰・現行どおり）＋ `templates/**`（再帰・テキストファイル）＋
`.claude/skills/**/*.md`（再帰）。除外は `docs/archive/`（当時の記録）と `work/` 自身。

`templates/` は `.md` 以外（`.yml`・`.py`）も対象にする — 壊れた参照はコメントに書かれる。
拡張子で絞らず、テキストとして読めるファイルを見る（バイナリは読み飛ばす）。

## 先に赤くする
現状で違反が出るはずなので、**検査を足して赤いことを確かめてから**直す。違反が 0 件なら、
それ自体が「範囲を広げても何も守っていない」証拠になるので、その事実を記録して閉じる
（作った検査が何も捕まえないなら、作った価値を主張しない）。

## 受け入れ基準
- 一時ディレクトリの fixture で、`templates/x.yml` と `.claude/skills/y/SKILL.md` の `work/EP-…` 参照が
  それぞれ error になる。
- `docs/archive/` と `work/` 配下は指摘されない。
- 現リポの違反を洗い出し、直すか、除外の理由を明記する。
- `uv run verify` 全成功。
