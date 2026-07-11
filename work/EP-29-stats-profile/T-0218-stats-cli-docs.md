---
id: T-0218
kind: task
status: todo
title: stats CLI（カタログ）と docs/stats.md の使い方導線を作る（coverage_lint に載せる）
created: 2026-07-11
depends_on: [T-0217]
verified_by: []
---
# T-0218 入口を作って完了にする

## 何が問題か
部品は「他の人が元コードを読まずに使える状態にして完了」。レジストリ（BAYES_MODELS・SAMPLERS・
BAYES_DIAGNOSTICS・PPC_CHECKS）ができても、カタログ CLI と正本 docs の使い方が無ければ入口の無い
カタログ＝嘘の入口になる。新しい CLI コマンドは正本 docs から使い方にたどり着ける記載が必須
（coverage_lint が未到達コマンドを verify で失敗にする）。

## やること
- `uv run stats` を新設（`pyproject の [project.scripts]`。ds の `data` と同じくプロファイル境界で
  モジュールを分ける）。サブコマンドは 4 レジストリのカタログ（`render_catalog` を使う。二重管理しない）と
  `--help`。extra 未導入なら導入ヒントを出して exit 1（`serve` と同じ作法）。
- `docs/stats.md` に使い方（宣言 → 推論 → 判定 → 採用の一巡と、各コマンド）を書き、AGENTS.md の
  コマンド節に 1 行足す（`data`／`serve`／`agent` と同じ形）。
- coverage_lint の導線検査に stats の全サブコマンドが載ることを確認する（免除は使わない）。

## やらないこと
- 推論を CLI から走らせる重いサブコマンド（カタログと案内が本タスクの範囲。実行の入口は実需要が来てから）。
- スキルの新設（docs 正本への記載で導線要件は満たせる。スキル化は使われ方が見えてから）。

## 受け入れ基準
- `uv run verify` 全成功（coverage_lint が新コマンドを未到達にしない・免除リストに stats が無い）。
- `uv run stats --help` と各カタログが動き、全項目に説明文が出る（説明文必須は registry が登録時に強制）。
- pymc 未導入（extra なし）の環境で `uv run stats` が導入ヒントを出して失敗する（黙って空を出さない）。
- 別の立場が `docs/stats.md` だけを読んで、極小モデルの一巡（宣言 → 推論 → 判定 → 採用）を再現できる。
