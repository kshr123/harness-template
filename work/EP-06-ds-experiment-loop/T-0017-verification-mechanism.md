---
id: T-0017
kind: task
status: todo
title: 検証の仕組み（段階×テストの目印の対応・未マーク失敗ガード）
requirements: [REQ-004]
depends_on: [T-0010]
created: 2026-07-03
owner: sakurada
---
# T-0017 検証の仕組み（段階×テストの目印）

## 目的
土台（テンプレート）として、検証の**段階（level）**と**テストの目印（marker）**を正しく対応づける。
この repo を土台にする全案件が、最初から「速い内側ループ＋端まで確かめる門番＋切り離せる重い層」を得る。
現在のテスト数が少ないことは作らない理由にしない（仕組みづくりだから理想形を組み込む）。詳細は `DESIGN.md` C。

## 決めごと（この仕組みの定義）
- **段階＝その瞬間に見合う検査の深さ**（累積）：fast（編集中）→ standard（コミット前）→ full（完了判定・CI＝`uv run verify`）。
- **目印＝テストの重さと範囲**：`unit` / `integration` / `e2e`（各テストにちょうど1つ）＋ `slow`（重いものに追加）。
- 対応（門番の段階は slow を絶対に含めない）：
  - fast … ruff format/check ＋ `pytest -q -m "unit and not slow"`
  - standard … ＋ mypy ＋ `pytest -q -m "integration and not slow"`
  - full … ＋ `pytest -q -m "e2e and not slow"`
  - slow … 段階に載せない。`pytest -q -m slow` を実験完了・夜間に明示的に叩く。

## 受け入れ基準（テスト先行で）
- `checks.toml` の各段階の pytest を上記の marker 選択にする。full まで通すと unit＋integration＋e2e が走り、slow は走らないことを確認。
- 既存テスト8ファイルに `pytestmark` でピラミッドの目印を1つずつ付ける（分類は DESIGN.md C のピラミッド表に従う。現状は大半が unit、ファイル IO・設定をまたぐものは integration）。
- **未マークのテストは失敗**：`tests/conftest.py` の `pytest_collection_modifyitems` で、unit/integration/e2e のいずれの目印も無い test item を collect エラーにする。故意に無印のテストを置いた確認テストで失敗を確かめる。
- `uv run verify`（full）にすべて成功する。段階ごとの選択が効いていること（`uv run check --level fast` が unit だけを走らせる等）を確認。
