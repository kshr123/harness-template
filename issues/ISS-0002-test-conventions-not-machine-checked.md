---
id: ISS-0002
kind: risk
state: resolved
found_in: 構造レビュー-2026-07
created: 2026-07-03
promoted_to: T-0069
title: テスト規約の一部が規約止まりで機械検査になっていない（seed・--test・xfail参照）
---
# ISS-0002 テスト規約の一部が規約止まりで機械検査になっていない（seed・--test・xfail参照）

## 事象
AGENTS のテスト規約のうち次の 3 つは「レビュー観点」で、違反しても verify が落ちない（機械検査が無い）：
- 乱数はグローバル種（`np.random.seed` 等）を使わない＝明示引数だけ（method G・DESIGN C・AGENTS）。
- 実験スクリプトは `--test`（スモーク）を必須にする（AGENTS・experiment スキル）。
- `skip`・`xfail` は課題（ISS-…）参照を必須にする（AGENTS）。

## 根拠・影響
DEC-0005 の進化のラチェット＝「2 回目が出たら機械検査へ昇格し、先に『違反すると失敗する検査』を書いて退行を止める」。
現状は退行を止める検査が無いので、雛形の複製で規約破りが黙って入りうる。対処すると決めたら、`work/**/code/*.py` の
グローバル種検出・`--test` 引数の有無検出・`@pytest.mark.xfail`/`skip` の理由に ISS 参照があるかの検査を
`pm.spec_lint`（または新設のテスト規約リンタ）に足すタスク（T-…）へ昇格する。まず赤テストを書いてから実装する。
