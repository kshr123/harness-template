---
id: T-0150
kind: task
status: done
title: docs/ds.md（DS プロファイルの Reference＝薄い地図）を足して serve/agent/ops と対称にする
created: 2026-07-07
depends_on: []
verified_by: [tests/test_doclint.py::test_real_repo_docs_have_no_dead_links]
---
# T-0150 docs/ds.md を足す（DS プロファイルの入口を1枚に）

## 背景
serve・agent・ops には各1枚の Reference（`docs/serve.md`・`docs/agent.md`・`docs/ops.md`）があり、README も
「正本は docs/xxx.md」と指している。DS プロファイルだけこの1枚が無い（歴史的な抜け＝ds は per-profile-doc の
型が定着する前に育った）。人が「この基盤で DS はどうやるのか」を1枚で掴めず、README の data 行も指す先が無い。

## 方針（薄く・二重管理を作らない）
DS の中身は既にある（進め方＝`docs/method.md`、手順＝experiment/eda/features スキル、部品＝`uv run data` の
カタログ、テーブル定義＝`docs/data/`）。ds.md は**それらを書き写さない**。**地図＋入口に徹する**：DS とは何か
（平易に）→ 学習の流れ（テーブル→探索→特徴量→実験→評価→保存・昇格→配信/バッチ予測→監視）を1行ずつ＋
どこにあるか・どのコマンド/スキルか → 詳細はそれぞれの正本へ誘導。契約・手順は再掲しない。

## 書き方（今回の書き方ルール）
- 造語を使わず本文だけで分かる。champion・cross-validation・OOF などは初出でその場に平易な一文。
- H1 直後に平易な導入（これは何か・なぜ・誰が読むか）。serve.md と同じ register。

## やること
1. `docs/ds.md` を新規作成（上の方針）。
2. `README.md` の data 行を「…のカタログ。正本は docs/ds.md」に更新（serve/agent 行と対称に）。
3. `docs/README.md` の文書地図に `ds.md`（Reference）の行を足す。

## 受け入れ基準
- `uv run verify` 全成功（doclint が ds.md 内のリンク切れ・README からの参照を検査）。
- 人が `docs/ds.md` 1枚で DS プロファイルの全体像（何があり・どこを見ればよいか）を掴める。内容の重複が無い
  （手順・契約は各正本へのリンクで済ませている）。README・docs/README から ds.md へ辿れる。

## 触ってよい範囲
`docs/ds.md`（新規）・`README.md`・`docs/README.md`・この item.md。他は変えない。
