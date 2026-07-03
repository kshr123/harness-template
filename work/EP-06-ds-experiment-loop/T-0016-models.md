---
id: T-0016
kind: task
status: done
title: モデル永続化・登録簿 models.py（Pipeline 丸ごと保存・版・台帳・昇格関門）
requirements: [REQ-004]
depends_on: [T-0013, T-0014]
verified_by:
  - tests/test_ds_models.py::test_save_load_roundtrip_and_feature_names
  - tests/test_ds_models.py::test_rejects_missing_manifest_tampered_and_bad_format
  - tests/test_ds_models.py::test_promotion_gate
created: 2026-07-03
closed: 2026-07-03
owner: sakurada
---
# T-0016 モデル永続化・登録簿 models.py

## 目的
学習済み Pipeline 丸ごとの保存・読込・一覧・昇格。store と同じ4作法（config URI・rename・指紋・manifest）。
設計は DESIGN.md B-5＋R（Serializer 注入は入れず「丸ごと pickle・format 文字列だけ差し替え口」に簡素化）。DEC-0007。

## 受け入れ基準（テスト先行で）
- `save_model`／`load_model`：pickle＋manifest・版=UTC時刻・再利用拒否・feature_names 自動（get_feature_names_out）・依存版は記録のみ。3段の門（manifest 無し/指紋不一致/形式!=pickle は拒否）。sklearn 非import。
- `list_models`（生成ビュー台帳）・`champion`・`promote_model`（絶対=passes かつ相対=primary で勝つ関門・追記のみ・保存は常に許す）。CLI `uv run data models`（champion に★）。
- `.gitignore` に `data/**/models/`（実体はコミットしない）。
- train.py が fit_final→save_model を接続（一気通貫）。
- `uv run verify` 全成功。
