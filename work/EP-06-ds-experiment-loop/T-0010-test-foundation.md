---
id: T-0010
kind: task
status: todo
title: テストの土台（フィクスチャ・マーカー・experiment完了検査・規約）
requirements: [REQ-004]
created: 2026-07-03
owner: sakurada
---
# T-0010 テストの土台

## 目的
実験ループをテスト先行で作るための土台を整える。テスト戦略（本セッションで決定）を仕組みに落とす。

## 受け入れ基準（テスト先行で。各項目にテストを付ける）
- `tests/conftest.py` に一時プロジェクトのフィクスチャ工場（config・テーブル定義YAML・work/ を持つ tmp_path プロジェクトを作る）。
- pytest マーカー（unit / integration / e2e / slow）を pyproject に登録。full は除外なしで全実行。
- **穴埋め(a)**：`pm.lint` に「done の実験（experiment）は結果記録（指標・設定・データ指紋のファイル）が必須」を追加（調査の「## 結論」検査と同型）。故意のケースで失敗を確認。
- **穴埋め(b)**：`verified_by` の検査を、ファイル存在だけでなく `::テスト名` がそのファイルに現れることまで確認するよう強化。
- 規約を `AGENTS.md` に明記：テストに書ける数値は「テストデータの構成から導出できるもの」だけ／実験スクリプトは `--test` を必須とする／skip・xfail は課題（ISS）参照を必須／乱数は明示引数・グローバル種禁止。
- `uv run verify` にすべて成功する。
