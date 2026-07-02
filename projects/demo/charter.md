---
project: demo
status: active
owner: sakurada
---
# プロジェクト憲章：demo（ハーネス自身の構築）

## 目的（この案件は何のために・誰の何を解決するか）
このハーネス自身を「最初の案件」として構築し、PM層（憲章→WBS→タスク→検証）が
実際に回ることを確かめる。使いながら「やりやすい・やりにくい」を learnings に記録し、
PM設計へ反映する（ドッグフーディング）。

## スコープ（やること／やらないこと）
- やる：PM層中核（charter・wbs・tasks・STATUS 導出・孤児検出・共通の検証コマンド）を動かす。
- やらない：ML/DSプロファイル（Phase 1）、配布テンプレ化（Phase 2）。

## 成功条件（どうなったら成功か。測れる形で）
- `uv run verify` が緑になる。
- 粗い WBS →着手が近い 1 エピックだけ detailed 化→タスク→done=緑 が 1 件通る。
- PM層の friction が learnings に 1 件以上記録され、対応方針が決まっている。

## 関係者（承認者＝PJ リーダー・依頼元の連絡先）
- 作業者：sakurada（DS 兼務）
- PJ リーダー（承認）：sakurada（1 人案件のため兼任）

## 制約（期限・技術・データ）
- 技術：uv / ruff / mypy(+ty) / typer / pydantic / polars(ML段) / Python 3.14。
- Windows 含むクロスプラットフォーム（make 非依存）。

## 未決点
- （なし。着手可）
