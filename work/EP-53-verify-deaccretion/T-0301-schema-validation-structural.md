---
id: T-0301
kind: task
status: done
created: 2026-07-31
closed: 2026-07-31
start: 2026-07-31
due: 2026-07-31
effort_days: 1
requirements: []
depends_on: []
verified_by:
  - tests/test_ds_schema.py::test_malformed_schema_is_rejected_at_construction
  - tests/test_ds_schema.py::test_data_lint_bad_dtype
---
# T-0301 テーブル定義の well-formedness を pydantic バリデータへ（(b)→(a)）

data_lint の**単一スキーマ内で閉じる**規則を `TableSchema` の構築時バリデータへ移す＝不正なスキーマ
オブジェクトを作れなくする（保証 (a)。lint（毎回走る (b)）で捕まえるより上流）。

- 移した（構築時に弾く）：dtype∈POLARS_DTYPES（Column バリデータ）・primary_key⊆列・target_column∈列
  （model_validator）。`load_schemas` は違反理由をそのまま problems に載せる（「N 件」でなく具体メッセージ）。
- **残した（data_lint）**：派生層（processed/split）は lineage 必須＝これは well-formed なオブジェクトでも
  拒む**リポの受け入れ方針**なので構築ゲートに載せない（store.save 等の無関係な経路まで巻き込まないため）。
  スキーマ間の規則（ID 重複・lineage 参照先の実在・越境参照）も data_lint に残す。
