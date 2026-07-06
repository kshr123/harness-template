---
id: EP-19
kind: epic
status: done
title: 生きたドキュメント（導線カバレッジの機械化＝missing link を verify で止める）
plan: detailed
requirements: [REQ-001]
depends_on: [EP-16]
created: 2026-07-06
---
# EP-19 生きたドキュメント（導線カバレッジの機械化）

## 目的（オーナーの不安に直接答える）
「開発・更新のたびにスキルとプロジェクト全体のドキュメントが進化するはずだが、更新されているか不安」への機械的な答え。
現状の `doclint`（参照実在検査）は**一方向**＝「参照先が在るか（dead link）」だけを見る。だが不安の本体は逆向き＝
**新しい能力（CLI コマンド・レジストリ種別・プロファイル）が増えたのに、対応するスキル/ドキュメントの導線が作られていない
（missing link）**を機械が捕まえられないこと。DEC-0009 の DoD 3 要件のうち①レジストリ登録②docstring は機械検査があるが、
**③「スキル/雛形からの導線」だけが未機械化**で、書き忘れても `uv run verify` は緑のまま。

## 実測した穴（裏取り済み）
`@data_app.command` は実在し `test_catalog` で緑なのに、`.claude/skills/**` から到達不能なコマンドがある：
`data selectors`・`data tuners`（スキル言及 0）ほか `data lint`/`data metrics`/`data predict`/`data experiments`/`data sources`。
serve スキルに `data monitor` の 1 行が入ったのは「今回のタスク作者が覚えていたから」で、忘れても検査は落ちない。これを直す。

## 取り込み判断（living-docs 調査）
- **採用（now）**：`coverage_lint`＝cli.py 群を ast 解析し `@*.command("name")` を全抽出、各コマンドがスキル/正本 docs に
  最低 1 回現れるか検査（未出現＝error）。免除は allowlist（コード上・なぜ免除かのコメント必須＝サイレントな見逃し防止）。
  core・stdlib のみ・profile を import しない（cli.py を**テキスト/AST として読む**＝doclint と同じ作法でプロファイル境界を壊さない）。
- **不採用**（過検査＝保守が重い・偽陽性が多い）：DEC→AGENTS/method の「昇格が反映されたか」自動検査（method B 節の
  「正本は 1 か所」と矛盾しうる・判定基準が無い＝レビュー観点のまま）／スキルの意味的鮮度スコアリング（signal 弱・harvest の人手棚卸しで足りる）／
  DEC 被参照グラフの可視化（14 DEC・12 スキルの規模ではオーバーエンジニアリング）。
- **Registry.catalog を別途舐める案は不採用**：`@*.command` 全抽出（coverage_lint）で代替でき、二重の仕組みを持たない方が良い。

## 進め方（テスト先書き・独立レビュー・verify 緑で done）
- **T-0088 導線カバレッジ検査**（`src/harness/coverage_lint.py`＝新規 core・`checks.py` の PM_CHECKS に配線・
  実測した既存欠落をスキルへ追記して緑化・AGENTS に 1 行＋強制点・learnings 記録→即 DEC）。歩く骨組み＝検査を先に red で
  確認→実装→既存欠落を埋めて green。DEC-0009 の第 3 要件を機械化する本体。

## この EP の範囲外（soon・別タスク）
プロファイル×スキルの粗い対応検査（`load_profiles` を使う＝profile 経由・3 個目のプロファイルが来たら）・`uv run check` 出力への
カバレッジ節の明示・harvest 手順に「免除リストの棚卸し」1 行。now が緑になってから DEC-0012 の基準で順次。

## 依存順
単独（core のみ・他プロファイルに非依存）。EP-20/EP-21 より先に入れると、以降の新コマンドの導線忘れを自動で止められる（基盤）。
