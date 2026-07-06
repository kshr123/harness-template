---
id: EP-16
kind: epic
status: in-progress
title: 型・機械検査・DX（ExperimentSpec・doclint・conventions lint・property テスト・複製DX）
plan: detailed
requirements: [REQ-001]
depends_on: [EP-15]
created: 2026-07-06
---
# EP-16 型・機械検査・DX（Wave 4）

## 目的
`docs/ideal-build-plan-2026-07-05.md` の Wave 4。DEC-0010 に基づき、正本ドリフトと規約違反を**機械で止める**層を厚くし、
実験 config を型付けし、複製（テンプレ）体験を機械化する。ISS-0002/0003/0007 を消化。

## タスク（依存順・各 1 PR・テスト先書き・独立レビュー・verify 緑で done）
- **T-0068 doclint**：スキル/AGENTS/method/learnings が参照する DEC・ISS・パス・`uv run` コマンドの実在検査を PM_CHECKS へ
  （正本ドリフトを機械で止める・ISS-0003 close）。
- **T-0070 property テスト**（hypothesis）：passes の NaN fail-closed・psi の性質・fixed_split の安定分割・fold 被覆（oof_mask）・
  エンコーダ不変量（scale の平均0/分散1 等）を不変条件で固定。
- **T-0067 ExperimentSpec**（pydantic・extra=forbid）：実験 config を型付け・`threshold`→`decision_threshold`・
  run_experiment を型付き spec 受けに（threshold/thresholds の取り違えを型で止める・ISS-0007）。
- **T-0069 conventions lint**（ISS-0002）：グローバル種検出・実験 `--test` 必須・skip/xfail の ISS 参照必須（conftest/検査拡張）。
- **T-0071 CliRunner スモーク＋カバレッジ・ラチェット**（CI 別ジョブ）／**T-0072 template-init**（複製の機械化＋複製後 verify）／
  **T-0073 Windows CI ジョブ**／status --next。

## やらないこと
skops 既定化（次のテンプレ複製時・owner 判断）。過度な型付け（config の自由度を殺さない範囲で）。
